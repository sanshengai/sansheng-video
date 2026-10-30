import contextlib
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import qa_delivery as qa

FFMPEG = shutil.which('ffmpeg')
PROFILE = {'delivery': {'loudness': {'douyin': -14, 'xhs': -14, 'shipinhao': -16, 'default': -16,
                                     'true_peak_max': -1.0, 'normalize_true_peak': -1.5}}}


def sh(*cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def measure_lufs(path):
    r = subprocess.run(['ffmpeg', '-nostats', '-i', str(path), '-af', 'ebur128=peak=true', '-f', 'null', '-'],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    log = r.stderr[r.stderr.rfind('Summary:'):]
    return float(re.search(r'I:\s+(-?[\d.]+)\s+LUFS', log).group(1))


def make_profile(root):
    d = Path(root) / 'profile'
    d.mkdir()
    (d / 'profile.json').write_text(json.dumps(PROFILE))
    return str(d)


def make_sine(path, gain_db, seconds):
    sh('ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i', f'sine=f=440:d={seconds}:r=48000',
       '-af', f'volume={gain_db}dB', str(path))


def make_video(path, audio, still_from=None, seconds=4):
    """360x640、30fps。still_from 给出时，该处起 5 秒是完全静止的纯色画面。"""
    size = '360x640'
    if still_from is None:
        vsrc = ['-f', 'lavfi', '-i', f'testsrc2=s={size}:r=30:d={seconds}']
        cmd = ['ffmpeg', '-y', '-v', 'error'] + vsrc + ['-i', str(audio), '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
               '-c:a', 'aac', '-shortest', str(path)]
        sh(*cmd)
        return
    parts = [f'testsrc2=s={size}:r=30:d={still_from}', f'color=c=0x336699:s={size}:r=30:d=5',
             f'testsrc2=s={size}:r=30:d=3']
    cmd = ['ffmpeg', '-y', '-v', 'error']
    for p in parts:
        cmd += ['-f', 'lavfi', '-i', p]
    cmd += ['-i', str(audio), '-filter_complex', '[0:v][1:v][2:v]concat=n=3:v=1:a=0,format=yuv420p[v]',
            '-map', '[v]', '-map', '3:a', '-c:v', 'libx264', '-c:a', 'aac', '-shortest', str(path)]
    sh(*cmd)


def run_cli(*argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = qa.main(list(argv))
    return code, buf.getvalue()


@unittest.skipUnless(FFMPEG, 'ffmpeg missing')
class DeliveryMeasureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        cls.root = root
        cls.profile = make_profile(root)
        # 响度：同一段正弦，一条偏低（约 -35 LUFS），一条校到 -16 LUFS 附近
        make_sine(root / 'low.wav', -17, 4)
        low = measure_lufs(root / 'low.wav')
        cls.low_lufs = low
        make_sine(root / 'ok.wav', -17 + (-16 - low), 4)
        make_video(root / 'low.mp4', root / 'low.wav')
        make_video(root / 'ok.mp4', root / 'ok.wav')
        # 静止 5 秒：音轨校到 -16，时间线分别把 read 放在静止段外/内
        make_sine(root / 'still.wav', -17 + (-16 - low), 11)
        make_video(root / 'still.mp4', root / 'still.wav', still_from=3)
        shots = [{'id': 'a', 'start': 0, 'end': 3}, {'id': 'b', 'start': 3, 'end': 8},
                 {'id': 'c', 'start': 8, 'end': 11}]
        for name, read in (('outside', (0.5, 2.0)), ('inside', (3.2, 7.8))):
            sh_ = json.loads(json.dumps(shots))
            host = 0 if name == 'outside' else 1
            sh_[host]['reads'] = [{'start': read[0], 'end': read[1], 'revealCompleteAt': read[0] + 0.2,
                                   'min_hold': 1.0, 'purpose': '读完'}]
            (root / f'{name}.json').write_text(json.dumps({'fps': 30, 'duration': 11, 'shots': sh_}))
        cls.out_a, cls.out_b = root / 'qa_out', root / 'qa_in'
        cls.code_a, _ = run_cli(str(root / 'still.mp4'), '--timeline', str(root / 'outside.json'),
                                '--platform', 'shipinhao', '--profile-dir', cls.profile, '--out', str(cls.out_a))
        cls.code_b, _ = run_cli(str(root / 'still.mp4'), '--timeline', str(root / 'inside.json'),
                                '--platform', 'shipinhao', '--profile-dir', cls.profile, '--out', str(cls.out_b))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_quiet_film_fails_loudness_then_passes_when_gain_fixed(self):
        out = self.root / 'qa_low'
        code, _ = run_cli(str(self.root / 'low.mp4'), '--platform', 'shipinhao',
                          '--profile-dir', self.profile, '--out', str(out))
        self.assertEqual(code, 1)
        text = (out / 'summary.md').read_text()
        self.assertIn('响度不达标', text)
        self.assertIn('-16', text)
        out = self.root / 'qa_ok'
        code, _ = run_cli(str(self.root / 'ok.mp4'), '--platform', 'shipinhao',
                          '--profile-dir', self.profile, '--out', str(out))
        self.assertEqual(code, 0, (out / 'summary.md').read_text())
        self.assertIn('响度达标', (out / 'summary.md').read_text())

    def test_missing_audio_fails_only_when_timeline_requires_audio(self):
        silent = self.root / 'silent.mp4'
        sh('ffmpeg', '-y', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=s=360x640:r=30:d=2',
           '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(silent))
        shots = [{'id': 'a', 'start': 0, 'end': 2}]
        for requires, expected in ((True, 1), (False, 0)):
            tl = self.root / f'silent-{requires}.json'
            tl.write_text(json.dumps({'fps': 30, 'duration': 2, 'requires_audio': requires, 'shots': shots}))
            out = self.root / f'qa_silent_{requires}'
            code, _ = run_cli(str(silent), '--timeline', str(tl), '--platform', 'shipinhao',
                              '--profile-dir', self.profile, '--out', str(out))
            with self.subTest(requires_audio=requires):
                self.assertEqual(code, expected, (out / 'summary.md').read_text())

    def test_still_outside_reads_is_listed_for_review(self):
        s = json.loads((self.out_a / 'summary.json').read_text())
        self.assertEqual(self.code_a, 0)
        self.assertEqual(len(s['frozen']['review']), 1)
        item = s['frozen']['review'][0]
        self.assertAlmostEqual(item['secs'], 5.0, delta=0.3)
        self.assertEqual(s['frozen']['design_hold'], [])
        self.assertIn('待查', (self.out_a / 'summary.md').read_text())

    def test_still_inside_read_is_design_hold(self):
        s = json.loads((self.out_b / 'summary.json').read_text())
        self.assertEqual(self.code_b, 0)
        self.assertEqual(len(s['frozen']['design_hold']), 1)
        self.assertEqual(s['frozen']['review'], [])

    def test_planned_cuts_translated_and_compared(self):
        s = json.loads((self.out_a / 'summary.json').read_text())
        self.assertEqual(s['cuts']['planned'], [3.0, 8.0])
        self.assertEqual(len(s['cuts']['matched']), 2, s['cuts'])

    def test_all_three_sheets_exist(self):
        from PIL import Image
        for name in ('hook_sheet.jpg', 'phone_sheet.jpg', 'beats_sheet.jpg'):
            p = self.out_a / name
            self.assertTrue(p.is_file() and p.stat().st_size > 0, name)
            with Image.open(p) as im:
                self.assertGreater(im.size[0], 0)
        self.assertTrue((self.out_a / 'report.json').is_file())
        self.assertTrue((self.out_a / 'report.md').is_file())


class PureFunctionTests(unittest.TestCase):
    def test_four_consecutive_cut_frames_merge_to_one(self):
        fps = 30
        cuts = [30 / fps, 31 / fps, 32 / fps, 33 / fps]
        self.assertEqual(len(qa.merge_cuts(cuts, fps)), 1)
        self.assertEqual(len(qa.merge_cuts(cuts + [90 / fps], fps)), 2)
        # 间隔 3 帧不合并
        self.assertEqual(len(qa.merge_cuts([1.0, 1.0 + 3 / fps], fps)), 2)

    def test_cut_compare_lists_missing_and_extra(self):
        r = qa.compare_cuts([3.0, 5.0], [3.0 + 2 / 30, 8.0], 30)
        self.assertEqual(len(r['matched']), 1)
        self.assertEqual(r['missing'], [8.0])
        self.assertEqual(r['extra'], [5.0])

    def test_platform_target_resolution(self):
        r = qa.resolve_targets(PROFILE, 'shipinhao')
        self.assertEqual((r['target_lufs'], r['true_peak_max']), (-16.0, -1.0))
        self.assertEqual(qa.resolve_targets(PROFILE, 'douyin')['target_lufs'], -14.0)
        self.assertEqual(qa.resolve_targets(PROFILE, 'bilibili')['target_lufs'], -16.0)
        self.assertEqual(qa.resolve_targets(PROFILE, 'true_peak_max')['target_lufs'], -16.0)
        self.assertEqual(qa.resolve_targets(None, 'douyin')['target_lufs'], -14.0)
        self.assertEqual(qa.resolve_targets({'delivery': {}}, None)['target_lufs'], -14.0)
        self.assertEqual(qa.resolve_targets({}, 'xhs')['true_peak_max'], -1.0)

    def test_loudness_judgement(self):
        self.assertTrue(qa.judge_loudness(-16.9, -3, -16, -1)[0])
        self.assertFalse(qa.judge_loudness(-17.2, -3, -16, -1)[0])
        self.assertFalse(qa.judge_loudness(-16, -0.5, -16, -1)[0])

    def test_frozen_classification_without_timeline(self):
        fr = [{'from': 0, 'to': 5, 'to_end': False}, {'from': 6, 'to': 7.5, 'to_end': False}]
        c = qa.classify_frozen(fr, [])
        self.assertEqual((len(c['review']), len(c['short_pause'])), (1, 1))
        c = qa.classify_frozen(fr, [(0.0, 2.4)])
        self.assertEqual(len(c['review']), 1)  # 2.4/5 < 一半
        c = qa.classify_frozen(fr, [(0.0, 2.5)])
        self.assertEqual(len(c['design_hold']), 1)

    def test_vendor_is_unmodified(self):
        vendor = SCRIPTS / 'vendor' / 'video-director'
        want = json.loads((vendor / 'UPSTREAM.json').read_text())['sha256']
        got = hashlib.sha256((vendor / 'qa_video.py').read_bytes()).hexdigest()
        self.assertEqual(got, want)


if __name__ == '__main__':
    unittest.main()
