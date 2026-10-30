import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import check_readability as cr

CLI = SCRIPTS / 'check_readability.py'


def tl(captions=(), reads=(), canvas=(1080, 1920)):
    events = [{'id': f'c{i}', 'start': s, 'end': e, 'caption': t}
              for i, (t, s, e) in enumerate(captions)]
    shot = {'id': 'sh', 'start': 0, 'end': 20}
    if reads:
        shot['reads'] = list(reads)
    return {'canvas': list(canvas), 'shots': [shot], 'events': events}


def read(text, end, reveal=0.0, **kw):
    r = {'start': 0, 'end': end, 'revealCompleteAt': reveal, 'min_hold': 1, 'purpose': 'x', 'text': text}
    r.update(kw)
    return r


def kinds(res):
    return [n['kind'] for n in res['notices']]


class CheckReadabilityTests(unittest.TestCase):
    def test_count_chars(self):
        self.assertEqual(cr.count_chars('AI 提示词 v2'), 5)
        self.assertEqual(cr.count_chars('你好，世界！'), 4)
        self.assertEqual(cr.count_chars(''), 0)

    def test_short_caption_flags_and_long_does_not(self):
        text = '一二三四五六七八九十一二'
        bad = cr.run(tl(captions=[(text, 0, 1)]), audience='adult')
        self.assertIn('读速', kinds(bad))
        self.assertIn('时长', kinds(bad))
        good = cr.run(tl(captions=[(text, 0, 3)]), audience='adult')
        self.assertNotIn('读速', kinds(good))
        self.assertNotIn('时长', kinds(good))

    def test_audience_speed_limits(self):
        eight = '一二三四五六七八'
        self.assertIn('读速', kinds(cr.run(tl(captions=[(eight, 0, 1)]), audience='learners')))
        self.assertNotIn('读速', kinds(cr.run(tl(captions=[(eight, 0, 1)]), audience='adult')))
        sixteen = '一二三四五六七八九十一二三四五六'
        self.assertNotIn('读速', kinds(cr.run(tl(captions=[(sixteen, 0, 2)]), audience='adult')))

    def test_split_needed_over_two_lines(self):
        self.assertIn('行数', kinds(cr.run(tl(captions=[('字' * 35, 0, 10)]), audience='adult')))
        self.assertNotIn('行数', kinds(cr.run(tl(captions=[('字' * 32, 0, 10)]), audience='adult')))

    def test_hold_formula(self):
        text = '一二三四五六七八九'
        self.assertIn('停留', kinds(cr.run(tl(reads=[read(text, 3.0)]), audience='adult')))
        self.assertNotIn('停留', kinds(cr.run(tl(reads=[read(text, 4.0)]), audience='adult')))
        res = cr.run(tl(reads=[read(text, 3.0)]), audience='adult')
        self.assertIn('3.5', res['notices'][0]['message'])

    def test_font_normalized_to_short_side(self):
        def r(px):
            return read('标题', 5, text_px=px, role='hook')
        self.assertIn('字号', kinds(cr.run(tl(reads=[r(80)]), audience='adult')))
        self.assertNotIn('字号', kinds(cr.run(tl(reads=[r(90)]), audience='adult')))
        self.assertNotIn('字号', kinds(cr.run(tl(reads=[r(60)], canvas=(720, 1280)), audience='adult')))
        self.assertIn('字号', kinds(cr.run(tl(reads=[r(50)], canvas=(720, 1280)), audience='adult')))

    def test_font_roles_and_texture(self):
        def run(px, role=None):
            extra = {'role': role} if role else {}
            return cr.run(tl(reads=[read('字', 5, text_px=px, **extra)]), audience='adult')
        self.assertIn('字号', kinds(run(40, 'term')))
        self.assertNotIn('字号', kinds(run(48, 'cta')))
        self.assertIn('字号', kinds(run(30)))
        self.assertNotIn('字号', kinds(run(32)))
        self.assertIn('只算纹理', run(20)['notices'][0]['message'])

    def test_terms(self):
        brief = '## 观看情境\n成人 横屏\n\n## 术语\n提示词\n\n## 已认可组合\n无\n'
        missing = cr.run(tl(captions=[('今天讲点别的', 0, 3)]), brief_text=brief)
        self.assertIn('术语', kinds(missing))
        found = cr.run(tl(captions=[('提示词是什么', 0, 3)]), brief_text=brief)
        self.assertNotIn('术语', kinds(found))
        in_read = cr.run(tl(reads=[read('提示词就是任务说明', 9)]), brief_text=brief)
        self.assertNotIn('术语', kinds(in_read))
        none = cr.run(tl(), brief_text='## 术语\n无\n')
        self.assertEqual(none['count'], 0)
        self.assertEqual(cr.parse_terms('- 提示词\n- 上下文、Agent，模型'), ['提示词', '上下文', 'Agent', '模型'])

    def test_audience_from_brief(self):
        brief = '## 观看情境\n初中生 竖屏\n\n## 术语\n无\n'
        res = cr.run(tl(), brief_text=brief)
        self.assertEqual(res['audience'], 'learners')
        self.assertEqual(cr.run(tl(), brief_text=brief, audience='adult')['audience'], 'adult')
        self.assertEqual(cr.run(tl(), brief_text='## 观看情境\n成人 横屏\n')['audience'], 'adult')

    def test_audience_line_and_negation(self):
        self.assertEqual(cr.run(tl(), brief_text='## 观看情境\n抖音 竖屏\n受众：成人，非学生\n')['audience'], 'adult')
        self.assertEqual(cr.run(tl(), brief_text='## 观看情境\n不面向学生，竖屏\n')['audience'], 'adult')
        self.assertEqual(cr.run(tl(), brief_text='## 观看情境\n竖屏\n受众：初中生\n')['audience'], 'learners')
        # 写了「受众：」一行时只看这一行，其他句子里的「学生」不再触发
        self.assertEqual(cr.run(tl(), brief_text='## 观看情境\n学生也可能看到\n受众：成人\n')['audience'], 'adult')

    def test_series_terms_checked_per_film(self):
        brief = '## 术语\n第 1 条：离线同步\n第 2 条：语音转写\n'
        timeline = tl(captions=[('离线同步不怕断网', 0, 3)])
        self.assertEqual(['语音转写'], [n['target'][3:-1] for n in cr.run(timeline, brief_text=brief)['notices']
                                      if n['kind'] == '术语'])
        self.assertEqual([], [n for n in cr.run(timeline, brief_text=brief, film=1)['notices'] if n['kind'] == '术语'])
        self.assertEqual(1, len([n for n in cr.run(timeline, brief_text=brief, film=2)['notices'] if n['kind'] == '术语']))

    def test_old_timeline_cli(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 't.json'
            p.write_text(json.dumps({'canvas': [1280, 720], 'shots': [{'id': 'a', 'start': 0, 'end': 2}],
                                     'events': [{'id': 'e', 'start': 0, 'end': 2}]}), encoding='utf-8')
            proc = subprocess.run([sys.executable, str(CLI), str(p), '--json'],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0)
            self.assertEqual(json.loads(proc.stdout)['count'], 0)

    def test_profile_caption_cps_overrides_default_limit(self):
        with tempfile.TemporaryDirectory() as d:
            prof = Path(d) / 'profile'
            prof.mkdir()
            (prof / 'profile.json').write_text(json.dumps({'delivery': {'caption_cps': {'default': 5}}}))
            p = Path(d) / 't.json'
            p.write_text(json.dumps(tl(captions=[('字' * 16, 0, 2)])), encoding='utf-8')
            def speed_notices(*extra):
                proc = subprocess.run([sys.executable, str(CLI), str(p), '--json', '--audience', 'adult', *extra],
                                      capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                return [n for n in json.loads(proc.stdout)['notices'] if '字/秒' in n['message']]
            empty = Path(d) / 'empty'
            empty.mkdir()
            (empty / 'profile.json').write_text('{}')
            self.assertEqual(speed_notices('--profile-dir', str(empty)), [])  # 8 字/秒，默认上限 9
            self.assertEqual(len(speed_notices('--profile-dir', str(prof))), 1)  # profile 上限 5
        self.assertEqual(cr.read_speed_limits({'delivery': {'caption_cps': {'learners': 'x'}}}), cr.READ_SPEED_MAX)

    def test_malformed_reads_is_input_error(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 't.json'
            p.write_text(json.dumps({'canvas': [1080, 1920], 'shots': [{'id': 'a', 'start': 0, 'end': 2, 'reads': 5}],
                                     'events': []}), encoding='utf-8')
            proc = subprocess.run([sys.executable, str(CLI), str(p)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 2, proc.stderr)
            self.assertNotIn('Traceback', proc.stderr)

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / 'bad.json'
            bad.write_text('not json', encoding='utf-8')
            self.assertEqual(subprocess.run([sys.executable, str(CLI), str(bad)],
                                            capture_output=True, text=True).returncode, 2)
            self.assertEqual(subprocess.run([sys.executable, str(CLI), str(Path(d) / 'none.json')],
                                            capture_output=True, text=True).returncode, 2)
            ok = Path(d) / 'ok.json'
            ok.write_text(json.dumps(tl(captions=[('字' * 12, 0, 1)])), encoding='utf-8')
            proc = subprocess.run([sys.executable, str(CLI), str(ok), '--json'],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0)
            self.assertGreater(json.loads(proc.stdout)['count'], 0)


if __name__ == '__main__':
    unittest.main()
