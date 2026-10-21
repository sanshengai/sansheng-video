"""Actual FFmpeg mixes exercise the review consumer, not a hearing detector.

Synthetic approval values below test schema/binding only. No fixture is human
listened or suitable music. Retained music/voice must not authorize a silent or
weakened action; a new pending review cannot inherit the old final-mix approval.
"""
import array
import copy
import json
import math
from pathlib import Path
import platform
import struct
import sys
import tempfile
import unittest
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mix_production_audio as mixer
from production_timeline import export, digest
from production_sound import preflight
from production_sound_review import current_plan, plan
from render_production import verify, prepare_review, check_review


def tone(path, frequency, gain, *, start=0, end=4):
    with wave.open(str(path), 'wb') as target:
        target.setparams((1, 2, 48000, 0, 'NONE', 'not compressed'))
        target.writeframes(b''.join(struct.pack('<h', round(4000 * gain * math.sin(i * math.tau * frequency / 48000)))
                                   if start <= i / 48000 < end else b'\0\0' for i in range(4 * 48000)))


def amplitude(path, frequency, start, end):
    import subprocess
    result = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-map', '0:a:0', '-ac', '1',
                             '-ar', '48000', '-f', 'f32le', '-'], capture_output=True, check=True)
    values = array.array('f'); values.frombytes(result.stdout)
    values = values[round(start * 48000):round(end * 48000)]
    angle = 2 * math.pi * frequency / 48000
    return 2 * math.hypot(sum(v * math.cos(angle * i) for i, v in enumerate(values)),
                          sum(v * math.sin(angle * i) for i, v in enumerate(values))) / len(values)


def project_fixture(root, video, gain=1, *, quiet=False, silent=False, distant=False, action_duck=False):
    """Real local media and preflight; parent is FFmpeg, not a claimed HF run."""
    root.mkdir()
    target, source = root / 'target.wav', root / 'source.mp4'
    tone(target, 2000, 0 if quiet else gain, start=1.5, end=1.7)
    command = ['ffmpeg', '-v', 'error', '-i', str(video)]
    if not silent:
        command += ['-i', str(target), '-map', '0:v:0', '-map', '1:a:0', '-c:a', 'aac']
    command += ['-c:v', 'copy', str(source)]
    mixer.run(command)
    event = {'id': 'contact', 'scene_id': 'one', 'start': 1.5, 'end': 1.7,
             'visual': {'type': 'synthetic-contact-fixture'}, 'timing_basis': 'authored'}
    if not quiet and not silent:
        event['sound_intent'] = {'role': 'action', 'prominence': 'distant' if distant else 'key',
                                 'reason': 'Synthetic action is intentionally distant.' if distant else 'Synthetic contact is the attention target.'}
        if action_duck:
            event['sound_intent']['music_duck'] = {'factor': .1, 'attack': .1, 'release': .25}
    data = {'fps': 30, 'duration': 4, 'canvas': [160, 90], 'requires_audio': not silent,
            'shots': [{'id': 'one', 'start': 0, 'end': 4}], 'events': [event],
            'sound_design': [{'scene_ids': ['one'], 'mode': 'quiet' if quiet or silent else 'source',
                              'reason': 'Deliberate quiet fixture.' if quiet or silent else 'Keep the action source.',
                              **({} if quiet or silent else {'source_elements': ['location']})}]}
    timeline, index = root / 'timeline.json', root / 'index.html'
    timeline.write_text(json.dumps(data))
    index.write_text('<div data-composition-id="fixture" data-duration="4">' +
                     ('' if quiet or silent else '<audio id="location" src="source.mp4" data-start="0" '
                      'data-duration="4" data-volume="1"></audio>') + '</div>')
    build = root / 'derived/production-build.json'
    metadata = export(timeline, build.parent, [index, source])
    wiring = preflight(root, data, metadata)
    receipt = source.with_suffix('.render.json')
    receipt.write_text(json.dumps({'kind': 'production-render/1', 'operation': 'synthetic-ffmpeg-test-only',
        'output': str(source), 'output_sha256': digest(source), 'build_path': str(build),
        'build_sha256': digest(build), 'sound_review_plan_sha256': wiring['review_plan_sha256'],
        'verification': {'has_audio': not silent}, 'runtime_roots': [], 'runtime_files': {},
        'host': {'system': platform.system(), 'release': platform.release(), 'machine': platform.machine()}}))
    return source, receipt


def synthetic_review_fixture(path):
    """Deliberately fabricated test input, never written as a production review."""
    data = json.loads(path.read_text())
    data['approved'] = True
    audio = data.get('audio_review')
    if audio:
        audio.update(status='listened', listener='synthetic test value only', playback='test value; no ears claimed')
        audio['checks'] = {key: 'pass' for key in audio['checks']}
        for row in audio['items']:
            row.update(outcome='appropriate' if row['id'].startswith('scene:') else 'clear',
                       note='Synthetic assertion only, not a listening observation.')
    return data


class SoundReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(); cls.root = Path(cls.temp.name).resolve()
        cls.video, cls.voice, cls.music = (cls.root / name for name in ('picture.mp4', 'voice.wav', 'music.wav'))
        mixer.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=s=160x90:r=30:d=4',
                   '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(cls.video)])
        tone(cls.voice, 700, .5, start=1, end=3)
        tone(cls.music, 1000, .5)
        cls.projects = {}
        for name, gain in (('normal', 1), ('weak', .02), ('muted', 0)):
            project = cls.root / name
            source, parent = project_fixture(project, cls.video, gain, action_duck=True)
            output = project / 'mixed.mp4'
            mixer.mix(source, cls.voice, cls.music, output, [[1, 3]], source_audio='preserve',
                      music_gain=.5, duck_gain=.2, parent_receipt=parent)
            review = project / 'final-review.json'
            prepare_review(project, output, review)
            cls.projects[name] = (project, output, review)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def check_fixture(self, name, value):
        project, output, review = self.projects[name]
        path = project / 'test-only-review.json'
        path.write_text(json.dumps(value))
        return check_review(project, output, path)

    def test_final_encoded_action_windows_require_listening_not_only_approval(self):
        project, output, review = self.projects['normal']
        value = json.loads(review.read_text()); value['approved'] = True
        with self.assertRaisesRegex(ValueError, 'listening is pending'):
            self.check_fixture('normal', value)
        page = review.with_suffix('.listen.html').read_text()
        self.assertIn('src="mixed.mp4"', page)
        self.assertNotIn('target.wav', page)
        data, _ = current_plan(project / 'derived/production-build.json')
        event = next(row for row in data['items'] if row['kind'] == 'event')
        self.assertEqual((1.5, 1.7, .5, 2.7), tuple(event[key] for key in ('start', 'end', 'context_start', 'context_end')))
        approved_fixture = synthetic_review_fixture(review)
        self.assertEqual('review_binding_current', self.check_fixture('normal', approved_fixture)['status'])
        for change in (lambda d: d['audio_review'].update(listener=None),
                       lambda d: d['audio_review'].update(items=[]),
                       lambda d: d['audio_review']['items'].pop(),
                       lambda d: d['audio_review']['items'][-1].update(outcome='intentionally_subtle'),
                       lambda d: d['audio_review']['checks'].update(level_relationships='pending')):
            value = copy.deepcopy(approved_fixture); change(value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.check_fixture('normal', value)

    def test_muted_and_weak_real_mixes_retain_other_lanes_but_cannot_inherit_review(self):
        normal_project, normal, normal_review = self.projects['normal']
        approved_fixture = synthetic_review_fixture(normal_review)
        for name in ('weak', 'muted'):
            _, output, review = self.projects[name]
            # These spectra establish the mutation, not an audibility standard.
            for hz in (700, 1000):
                self.assertAlmostEqual(1, amplitude(output, hz, 1.53, 1.67) /
                                       amplitude(normal, hz, 1.53, 1.67), delta=.05)
            self.assertLess(amplitude(output, 2000, 1.53, 1.67) /
                            amplitude(normal, 2000, 1.53, 1.67), .04)
            value = json.loads(review.read_text()); value['approved'] = True
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'listening is pending'):
                self.check_fixture(name, value)
            # Even rebinding outer technical hashes cannot transplant old ears.
            value['audio_review'] = approved_fixture['audio_review']
            with self.assertRaisesRegex(ValueError, 'current final mix'):
                self.check_fixture(name, value)

    def test_actual_mixer_smoothly_ducks_music_at_source_event_without_ducking_voice(self):
        _, output, _ = self.projects['normal']
        before, during, after = (amplitude(output, 1000, a, b) for a, b in ((1.2, 1.3), (1.54, 1.66), (2, 2.1)))
        self.assertAlmostEqual(.25, during / before, delta=.04)
        self.assertAlmostEqual(1, after / before, delta=.04)
        self.assertAlmostEqual(1, amplitude(output, 700, 1.54, 1.66) / amplitude(output, 700, 1.2, 1.3), delta=.04)
        receipt = json.loads(output.with_suffix('.mix.json').read_text())
        self.assertEqual([{'id': 'event:contact', 'start': 1.5, 'end': 1.7,
                           'factor': .1, 'attack': .1, 'release': .25}], receipt['event_music_ducks'])

    def test_missing_plan_false_audio_flag_and_removed_window_rejected(self):
        project, output, _ = self.projects['normal']
        receipt = output.with_suffix('.render.json'); original = receipt.read_bytes()
        value = json.loads(original)
        for change in (lambda d: d.pop('sound_review_plan_sha256'),
                       lambda d: d['verification'].update(has_audio=False)):
            altered = copy.deepcopy(value); change(altered); receipt.write_text(json.dumps(altered))
            with self.assertRaises(ValueError): verify(receipt)
            receipt.write_bytes(original)
        build = project / 'derived/production-build.json'; before = build.read_bytes()
        plan_path = project / 'derived/sound-review-plan.json'; plan_before = plan_path.read_bytes()
        altered = json.loads(plan_before); altered['items'].pop(); plan_path.write_text(json.dumps(altered))
        metadata = json.loads(before); metadata['outputs'][plan_path.name] = digest(plan_path)
        build.write_text(json.dumps(metadata))
        with self.assertRaisesRegex(ValueError, 'differs from the existing timeline'):
            current_plan(build)
        build.write_bytes(before); plan_path.write_bytes(plan_before)

    def test_quiet_distant_and_silent_intents_are_not_forced_loud(self):
        for name, options in (('quiet', {'quiet': True}), ('distant', {'distant': True}), ('silent', {'silent': True})):
            project = self.root / name
            output, _ = project_fixture(project, self.video, **options)
            review = project / 'review.json'
            prepare_review(project, output, review)
            value = synthetic_review_fixture(review)
            if name == 'distant': value['audio_review']['items'][-1]['outcome'] = 'intentionally_subtle'
            review.write_text(json.dumps(value))
            self.assertEqual('review_binding_current', check_review(project, output, review)['status'])
            if name == 'silent': self.assertNotIn('audio_review', value)

    def test_no_missing_or_invalid_intent_in_new_render_and_no_overwrite(self):
        data = {'requires_audio': True, 'duration': 2, 'shots': [{'id': 'a', 'start': 0, 'end': 2}],
                'events': [{'id': 'a', 'scene_id': 'a', 'start': 1, 'end': 2,
                            'sound': {'duration': .2}}]}
        with self.assertRaisesRegex(ValueError, 'sound_intent missing'): plan(data, require_intent=True)
        for invalid in (None, {}, {'role': 'action', 'prominence': 'key', 'reason': ' '}):
            data['events'][0]['sound_intent'] = invalid
            with self.assertRaisesRegex(ValueError, 'invalid sound_intent'): plan(data)
        project, output, review = self.projects['normal']
        before = review.read_bytes()
        with self.assertRaisesRegex(ValueError, 'review exists'): prepare_review(project, output, review)
        self.assertEqual(before, review.read_bytes())
        with self.assertRaises(ValueError): prepare_review(project, output, project / 'timeline.json', refresh=True)


if __name__ == '__main__':
    unittest.main()
