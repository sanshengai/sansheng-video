import copy
import json
import math
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from generate_sfx_tags import digest, plan
from production_sound import decisions, preflight
from production_timeline import export
from render_production import render


class ProductionSoundTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / 'timeline.json'
        self.index = self.root / 'index.html'
        self.audio = self.root / 'tone.wav'
        # A real non-silent fixture; no claim that it is a suitable music asset.
        with wave.open(str(self.audio), 'wb') as output:
            output.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
            output.writeframes(b''.join(struct.pack('<h', round(2000 * math.sin(i * math.tau * 440 / 8000)))
                                         for i in range(16000)))
        self.lock = self.root / 'assets.lock.json'
        self.lock.write_text(json.dumps({'items': [{'id': 'tone', 'revision': 'v1', 'scene_id': 'one',
            'project_path': 'tone.wav', 'sha256': digest(self.audio)}]}))
        self.data = {'fps': 30, 'duration': 2, 'canvas': [160, 90], 'requires_audio': True,
            'shots': [{'id': 'one', 'start': 0, 'end': 2}],
            'events': [{'id': 'cue', 'scene_id': 'one', 'start': 0, 'end': 2, 'timing_basis': 'authored',
                        'sound': {'asset_id': 'tone', 'revision': 'v1', 'duration': 2, 'volume': .2}}],
            'sound_design': [{'scene_ids': ['one'], 'mode': 'supplement',
                              'reason': 'Technical fixture: one continuous audible track.'}]}
        self.html = '<div id="root" data-composition-id="test" data-duration="2">\n</div>\n'
        self.index.write_text(self.html)

    def compile(self, *, wire=True, omit=()):
        self.source.write_text(json.dumps(self.data))
        dependencies = [p for p in (self.index, self.lock, self.audio) if p.name not in omit]
        export(self.source, self.root / 'derived', dependencies, refresh=True)
        if wire and any('sound' in event for event in self.data['events']):
            _, updated, _, _ = plan(self.index, self.lock, self.root / 'derived/sound-cues.json')
            self.index.write_text(updated)
            export(self.source, self.root / 'derived', dependencies, refresh=True)
        return json.loads((self.root / 'derived/production-build.json').read_text())

    def consume(self):
        # Invoke the actual render entry. A valid preflight reaches the missing
        # browser; defects must fail earlier without launching any renderer.
        return render(self.root, self.source, self.root / 'missing-runtime',
                      self.root / 'missing-browser', self.root / 'out.mp4')

    def test_supplement_is_wired_and_checked_on_actual_render_entry(self):
        build = self.compile()
        result = preflight(self.root, self.data, build)
        self.assertEqual('wired_not_listened', result['status'])
        self.assertEqual(1, result['supplemental_cues'])
        with self.assertRaisesRegex(ValueError, 'explicit local browser missing'):
            self.consume()

    def test_taken_but_unwired_asset_rejected_before_encoder(self):
        self.compile(wire=False)
        with self.assertRaisesRegex(ValueError, 'not wired into HTML'):
            self.consume()

    def test_empty_missing_and_unresolved_design_rejected_on_real_path(self):
        for value in ([], None, [{}]):
            with self.subTest(value=value):
                self.data['sound_design'] = value
                with self.assertRaises(ValueError):
                    self.compile(wire=False)
        del self.data['sound_design']
        # Old event export remains readable, but no longer passes new rendering
        # as a designed soundtrack merely because requires_audio is true.
        self.compile()
        with self.assertRaisesRegex(ValueError, 'sound_design missing'):
            self.consume()

    def test_decision_coverage_reason_mode_and_false_supplement_are_rejected(self):
        original = copy.deepcopy(self.data)
        changes = [lambda d: d['sound_design'][0].update(scene_ids=[]),
                   lambda d: d['sound_design'][0].update(scene_ids=['unknown']),
                   lambda d: d['sound_design'][0].update(scene_ids=['one', 'one']),
                   lambda d: d['sound_design'].append(copy.deepcopy(d['sound_design'][0])),
                   lambda d: d['sound_design'][0].update(reason=' '),
                   lambda d: d['sound_design'][0].update(mode='ambience-only-unimplemented'),
                   lambda d: d['sound_design'][0].update(mode='source'),
                   lambda d: d['sound_design'][0].update(mode='quiet'),
                   lambda d: d['events'][0]['sound'].update(volume=0),
                   lambda d: d['events'][0].pop('sound')]
        for change in changes:
            self.data = copy.deepcopy(original)
            change(self.data)
            with self.subTest(data=self.data), self.assertRaises(ValueError):
                self.compile(wire=False)

    def test_missing_changed_excerpt_or_unbound_asset_cannot_render(self):
        for omitted in ('tone.wav', 'assets.lock.json'):
            self.index.write_text(self.html)
            self.compile(omit=[omitted])
            with self.subTest(omitted=omitted), self.assertRaisesRegex(ValueError, 'absent from production dependencies'):
                self.consume()
        self.index.write_text(self.html)
        self.compile()
        self.audio.write_bytes(self.audio.read_bytes() + b'changed')
        with self.assertRaisesRegex(ValueError, 'stale production build'):
            self.consume()
        # A newly fingerprinted file still cannot bypass the adopted excerpt's lock.
        self.compile(wire=False)
        with self.assertRaisesRegex(ValueError, '哈希不符'):
            self.consume()
        self.audio.unlink()
        with self.assertRaisesRegex(ValueError, 'stale production build'):
            self.consume()

    def test_removed_moved_muted_or_wrong_track_cue_rejected_after_recompile(self):
        self.compile()
        valid_html = self.index.read_text()
        changes = [lambda s: self.html,
                   lambda s: s.replace('data-start="0"', 'data-start="0.1"'),
                   lambda s: s.replace('data-volume="0.2"', 'data-volume="0"'),
                   lambda s: s.replace('<audio ', '<audio muted '),
                   lambda s: s.replace('data-track-index="0"', 'data-track-index="7"'),
                   lambda s: s.replace('</audio>', '</audio><audio id="cue" src="tone.wav"></audio>')]
        for change in changes:
            self.index.write_text(change(valid_html))
            self.compile(wire=False)
            with self.subTest(html=self.index.read_text()), self.assertRaisesRegex(ValueError, 'not wired|重复 HTML id'):
                self.consume()

    def quiet(self, *, requires_audio=True):
        self.data['requires_audio'] = requires_audio
        self.data['events'][0] = {'id': 'visual', 'scene_id': 'one', 'start': 0, 'end': 2,
                                 'timing_basis': 'authored', 'visual': {'type': 'hold'}}
        self.data['sound_design'] = [{'scene_ids': ['one'], 'mode': 'quiet',
                                     'reason': 'Leave room for the spoken explanation; no added bed here.'}]
        self.index.write_text(self.html)

    def test_deliberate_quiet_and_silent_film_do_not_require_library_or_cues(self):
        for audio in (True, False):
            self.quiet(requires_audio=audio)
            build = self.compile()
            result = preflight(self.root, self.data, build)
            self.assertEqual(0, result['supplemental_cues'])
            with self.assertRaisesRegex(ValueError, 'explicit local browser missing'):
                self.consume()

    def source_sound(self):
        self.quiet()
        self.data['sound_design'] = [{'scene_ids': ['one'], 'mode': 'source',
            'reason': 'Retain the usable location recording.', 'source_elements': ['location']}]
        self.index.write_text(self.html.replace('</div>', '<audio id="location" src="tone.wav" '
            'data-start="0" data-duration="2" data-volume="0.4" data-track-index="1"></audio></div>'))

    def test_retained_sound_is_bound_to_real_unmuted_project_media(self):
        self.source_sound()
        build = self.compile()
        self.assertEqual(['location'], preflight(self.root, self.data, build)['retained_elements'])
        with self.assertRaisesRegex(ValueError, 'explicit local browser missing'):
            self.consume()
        valid = self.index.read_text()
        for change, message in ((lambda s: self.html, 'element missing'),
                       (lambda s: s.replace('<audio ', '<audio muted '), 'muted'),
                       (lambda s: s.replace('data-volume="0.4"', 'data-volume="0"'), 'volume: invalid'),
                       (lambda s: s.replace('data-duration="2" data-volume', 'data-duration="1" data-volume'), 'does not cover'),
                       (lambda s: s.replace('src="tone.wav"', 'src="https://example.invalid/tone.wav"'), 'project-local')):
            self.index.write_text(change(valid))
            self.compile(wire=False)
            with self.subTest(html=self.index.read_text()), self.assertRaisesRegex(ValueError, message):
                self.consume()

    def test_stale_auto_sound_cannot_hide_in_an_unnamed_tag(self):
        self.quiet()
        self.index.write_text(self.html.replace('</div>', '<audio data-sfx-auto="1" src="tone.wav" '
            'data-start="0" data-duration="2"></audio></div>'))
        self.compile(wire=False)
        with self.assertRaisesRegex(ValueError, 'absent from the timeline'):
            self.consume()

    def test_unplanned_old_silent_source_remains_supported(self):
        self.quiet(requires_audio=False)
        del self.data['sound_design']
        self.compile()
        with self.assertRaisesRegex(ValueError, 'explicit local browser missing'):
            self.consume()


if __name__ == '__main__':
    unittest.main()
