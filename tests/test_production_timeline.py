import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import wave

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import production_timeline as production
import production_narration as narration
from generate_sfx_tags import plan as sfx_plan


def timeline():
    return {'fps': 30, 'duration': 4, 'canvas': [1280, 720], 'requires_audio': False,
            'shots': [{'id': 'one', 'start': 0, 'end': 4}],
            'events': [{'id': 'point', 'scene_id': 'one', 'start': 1, 'end': 3,
                        'caption': '让复杂变清楚', 'visual': {'type': 'reading-card'}, 'timing_basis': 'authored'}]}


class ProductionTimelineTests(unittest.TestCase):
    def narrated_fixture(self, root):
        audio = root / 'speech.wav'
        with wave.open(str(audio), 'wb') as out:
            out.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
            out.writeframes(b'\0\0' * 16000)
        record = root / 'record.json'
        record.write_text(json.dumps({'audio': {'path': str(audio), 'sha256': narration.digest(audio),
            'duration': 2, 'text': '先观察。再比较。', 'chunks': [
                {'text': '先观察。', 'at': 0, 'duration': .8},
                {'text': '再比较。', 'at': 1, 'duration': 1}]}}))
        evidence = root / 'evidence.json'
        evidence.write_text(json.dumps(narration.import_evidence(record, audio)))
        data = timeline()
        data.update(requires_audio=True, narration={'evidence': 'evidence.json', 'offset': .5})
        data['events'][0].update(start=.5, end=1.3, caption='先观察。',
                                  timing_basis='verified_audio', narration_block=0)
        source = root / 'timeline.json'
        source.write_text(json.dumps(data))
        return data, source, evidence, record, audio

    def test_narration_real_blocks_export_dependencies_and_visual_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            data, source, evidence, record, audio = self.narrated_fixture(root)
            dest = root / 'derived'
            result = production.export(source, dest)
            for dependency in (evidence, record, audio, Path(narration.__file__).resolve()):
                self.assertEqual(narration.digest(dependency), result['inputs'][str(dependency)])
            self.assertEqual(500, json.loads((dest / 'captions.json').read_text())[0]['startMs'])
            self.assertIn('existing_production_block_offsets', (dest / 'events.js').read_text())
            del data['events'][0]['caption']
            source.write_text(json.dumps(data))
            production.export(source, dest, refresh=True)
            self.assertEqual([], json.loads((dest / 'captions.json').read_text()))
            for path in (evidence, record, audio):
                original = path.read_bytes()
                path.write_bytes(original + b' ')
                with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'stale'):
                    production.check(dest / 'production-build.json')
                path.write_bytes(original)

    def test_narration_rejects_false_evidence_text_time_and_silence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            original, source, evidence, record, audio = self.narrated_fixture(root)
            changes = [lambda d: d.update(requires_audio=False),
                       lambda d: d['events'][0].update(caption='部分文字'),
                       lambda d: d['events'][0].update(end=1.2),
                       lambda d: d['events'][0].update(narration_block=True),
                       lambda d: d['events'][0].update(narration_block=2),
                       lambda d: d['events'][0].update(timing_basis='estimated'),
                       lambda d: d['narration'].update(offset=3)]
            for change in changes:
                data = copy.deepcopy(original)
                change(data)
                source.write_text(json.dumps(data))
                with self.subTest(data=data), self.assertRaises(ValueError):
                    production.export(source, root / 'derived')
            source.write_text(json.dumps(original))
            actual = evidence.read_text()
            evidence.write_text(json.dumps({'kind': 'production-narration-blocks/1'}))
            with self.assertRaises(ValueError):
                production.export(source, root / 'derived')
            evidence.write_text(actual)
            audio.write_bytes(audio.read_bytes() + b'changed')
            with self.assertRaisesRegex(ValueError, 'audio SHA256'):
                production.export(source, root / 'derived')

    def test_narration_change_after_verification_rejected_before_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            _, source, evidence, record, audio = self.narrated_fixture(root)
            original = production.products
            def changed(*args):
                result = original(*args)
                audio.write_bytes(audio.read_bytes() + b'changed')
                return result
            with mock.patch.object(production, 'products', side_effect=changed):
                with self.assertRaisesRegex(ValueError, 'changed after verification'):
                    production.export(source, root / 'derived')
            self.assertFalse((root / 'derived/production-build.json').exists())

    def test_input_changes_while_writing_outputs_rejected_before_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            _, source, _, _, audio = self.narrated_fixture(root)
            original = Path.write_text
            def changed(path, *args, **kwargs):
                result = original(path, *args, **kwargs)
                if path.name == 'events.js':
                    audio.write_bytes(audio.read_bytes() + b'changed')
                return result
            with mock.patch.object(Path, 'write_text', changed):
                with self.assertRaisesRegex(ValueError, 'input changed while writing'):
                    production.export(source, root / 'derived')
            self.assertFalse((root / 'derived/production-build.json').exists())

    def test_one_event_moves_all_real_consumer_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            audio = root / 'tone.wav'
            with wave.open(str(audio), 'wb') as out:
                out.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
                out.writeframes(b'\0\0' * 2000)
            lock = root / 'assets.lock.json'
            lock.write_text(json.dumps({'items': [{'id': 'tone', 'revision': '1', 'scene_id': 'one',
                'project_path': 'tone.wav', 'sha256': hashlib.sha256(audio.read_bytes()).hexdigest()}]}))
            index = root / 'index.html'
            index.write_text('<html><body><div data-composition-id="root" data-duration="4"></div></body></html>')
            source = root / 'timeline.json'
            data = timeline()
            data['requires_audio'] = True
            data['events'][0]['sound'] = {'asset_id': 'tone', 'revision': '1', 'duration': .25}
            for start in (1, 1.5):
                data['events'][0]['start'] = start
                source.write_text(json.dumps(data))
                production.export(source, root / 'derived', refresh=start != 1)
                _, _, fragment, _ = sfx_plan(index, lock, root / 'derived/sound-cues.json')
                self.assertIn(f'data-start="{start:g}"', fragment)
                captions = json.loads((root / 'derived/captions.json').read_text())
                self.assertEqual(round(start * 1000), captions[0]['startMs'])
                # Execute the generated JS in the same global shape used by the HTML consumer.
                js = (root / 'derived/events.js').read_text()
                result = subprocess.run(['node', '-e', 'global.window={};' + js +
                    'console.log(window.productionTimeline.events[0].start)'], check=True, text=True, capture_output=True)
                self.assertEqual(start, float(result.stdout))

    def test_source_changes_during_export_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            source = root / 'timeline.json'
            data = timeline()
            source.write_text(json.dumps(data))
            original = production.products
            def changed(value):
                result = original(value)
                data['events'][0]['caption'] = '改变后的文字'
                source.write_text(json.dumps(data))
                return result
            with mock.patch.object(production, 'products', side_effect=changed):
                with self.assertRaisesRegex(ValueError, 'source changed during export'):
                    production.export(source, root / 'derived')
            self.assertFalse((root / 'derived/production-build.json').exists())

    def test_intentional_silence_has_no_fake_cue_or_caption(self):
        data = timeline()
        del data['events'][0]['caption']
        result = production.products(data)
        self.assertEqual([], json.loads(result['sound-cues.json']))
        self.assertEqual('', result['captions.srt'])
        data['events'][0]['sound'] = {'asset_id': 'x', 'revision': '1', 'duration': .2}
        with self.assertRaisesRegex(ValueError, 'silence'):
            production.products(data)

    def test_rejects_empty_outside_duplicate_and_fake_precision(self):
        mutations = [lambda d: d.update(events=[]), lambda d: d.update(shots=[]),
                     lambda d: d['events'][0].update(end=5),
                     lambda d: d['events'].append(copy.deepcopy(d['events'][0])),
                     lambda d: d['events'][0].update(timing_basis='verified_audio'),
                     lambda d: d['events'][0].update(start=float('nan'))]
        for mutate in mutations:
            data = timeline()
            mutate(data)
            with self.subTest(data=data), self.assertRaises(ValueError):
                production.products(data)

    def test_optional_read_text_fields_are_checked_only_when_present(self):
        read = {'start': 1, 'end': 3, 'revealCompleteAt': 1.2, 'min_hold': 1.5, 'purpose': '读完结论'}
        data = timeline()
        data['shots'][0]['reads'] = [dict(read)]
        production.products(data)
        data['shots'][0]['reads'] = [dict(read, text='让复杂变清楚', text_px=64, role='term')]
        production.products(data)
        for bad in ({'text': ' '}, {'text_px': 0}, {'text_px': True}, {'role': 'title'}):
            data = timeline()
            data['shots'][0]['reads'] = [dict(read, **bad)]
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                production.products(data)

    def test_stale_input_dependency_generated_output_and_missing_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            source, voice = root / 'timeline.json', root / 'voice.wav'
            source.write_text(json.dumps(timeline()))
            voice.write_bytes(b'actual dependency bytes')
            dest = root / 'derived'
            production.export(source, dest, [voice])
            receipt = dest / 'production-build.json'
            self.assertEqual('current_not_reviewed', production.check(receipt)['status'])
            for path in (source, voice, dest / 'events.js'):
                before = path.read_bytes()
                path.write_bytes(before + b' ')
                with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'stale'):
                    production.check(receipt)
                path.write_bytes(before)
            voice.unlink()
            with self.assertRaisesRegex(ValueError, 'stale'):
                production.check(receipt)
            data = timeline()
            data['events'][0].update(timing_basis='verified_audio', timing_evidence='missing.json')
            source.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'missing'):
                production.export(source, dest, refresh=True)

    def test_existing_output_requires_explicit_refresh(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            source = root / 'timeline.json'
            source.write_text(json.dumps(timeline()))
            production.export(source, root / 'derived')
            with self.assertRaisesRegex(ValueError, 'refresh'):
                production.export(source, root / 'derived')


if __name__ == '__main__':
    unittest.main()
