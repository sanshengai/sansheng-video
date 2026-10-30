import json
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import check_brief as cb

TABLE = "| 大致时间 | 发生什么 |\n|---|---|\n| 0-3秒 | 开场 |\n"
EMPTY_TABLE = "| 大致时间 | 发生什么 |\n|---|---|\n"


def brief(drop=(), override=None, extra=None):
    s = {
        "一句话主张": "慢就是快",
        "观看情境": "抖音 竖屏 60 秒 成人 静音",
        "开头 3 秒": "字卡：慢就是快",
        "术语": "无",
        "已认可组合": "v3 字体 48",
        "结构候选": "A\nB\nC 选 A",
        "视觉母题与强调色": "沙漏，橙色",
        "段落表": TABLE,
        "系列范围": "三条",
    }
    s.update(override or {})
    s.update(extra or {})
    return "".join("## %s\n%s\n\n" % (k, v) for k, v in s.items() if k not in drop)


class CheckBriefTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def profile(self, feed):
        d = self.dir / "prof"
        d.mkdir(exist_ok=True)
        (d / "profile.json").write_text(json.dumps({"delivery": {"feed_platforms": feed}}))
        return str(d)

    def run_cli(self, text, *args, feed=("douyin", "shipinhao", "xhs")):
        f = self.dir / "brief.md"
        f.write_text(text, encoding="utf-8")
        argv = [str(f), "--json", "--profile-dir", self.profile(list(feed)), *args]
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cb.main(argv)
        return code, json.loads(buf.getvalue())

    def test_new_complete_passes(self):
        code, r = self.run_cli(brief())
        self.assertEqual(code, 0, r)

    def test_missing_heading_fails(self):
        code, r = self.run_cli(brief(drop=["结构候选"]))
        self.assertEqual(code, 1)
        self.assertTrue(any("结构候选" in m for m in r["missing"]))

    def test_empty_content_fails(self):
        code, r = self.run_cli(brief(override={"一句话主张": "<!-- 待填 -->"}))
        self.assertEqual(code, 1)
        self.assertTrue(any("一句话主张" in m for m in r["missing"]))

    def test_header_only_table_fails(self):
        code, r = self.run_cli(brief(override={"段落表": EMPTY_TABLE}))
        self.assertEqual(code, 1)
        self.assertTrue(any("段落表" in m for m in r["missing"]))

    def test_exemption_without_reason_fails(self):
        for t in ("豁免：", "豁免:  "):
            code, r = self.run_cli(brief(override={"开头 3 秒": t}), "--platform", "抖音")
            self.assertEqual(code, 1, t)
            self.assertTrue(any("开头 3 秒" in m for m in r["missing"]))

    def test_exemption_with_reason_passes(self):
        code, r = self.run_cli(brief(override={"开头 3 秒": "豁免：剧情片，靠人物关系留人"}), "--platform", "抖音")
        self.assertEqual(code, 0, r)

    def test_bilibili_landscape_no_hook_passes(self):
        code, r = self.run_cli(brief(drop=["开头 3 秒"], override={"观看情境": "B站 横屏 10 分钟"}),
                               "--platform", "bilibili")
        self.assertEqual(code, 0, r)

    def test_platform_detected_from_body(self):
        code, r = self.run_cli(brief(drop=["开头 3 秒"], override={"观看情境": "视频号 竖屏"}))
        self.assertEqual(code, 1)
        self.assertEqual(r["platform"], "shipinhao")
        self.assertTrue(any("开头 3 秒" in m for m in r["missing"]))

    def test_continue_and_series_modes(self):
        code, r = self.run_cli(brief(drop=["已认可组合"]), "--mode", "continue")
        self.assertEqual(code, 1)
        self.assertTrue(any("已认可组合" in m for m in r["missing"]))
        code, r = self.run_cli(brief(drop=["系列范围"]), "--mode", "series")
        self.assertEqual(code, 1)
        self.assertTrue(any("系列范围" in m for m in r["missing"]))
        code, r = self.run_cli(brief(drop=["结构候选", "视觉母题与强调色"]), "--mode", "continue")
        self.assertEqual(code, 0, r)

    def test_too_many_terms_notice_only(self):
        code, r = self.run_cli(brief(override={"术语": "甲、乙，丙, 丁"}))
        self.assertEqual(code, 0, r)
        self.assertTrue(any("术语" in n for n in r["notices"]))

    def test_series_terms_counted_per_film(self):
        ok = brief(override={"术语": "第 1 条：离线同步\n第 2 条：语音转写\n第 3 条：模板库、模板市场"})
        code, res = self.run_cli(ok, "--mode", "series", "--platform", "xhs")
        self.assertEqual(code, 0)
        self.assertEqual(res["notices"], [])
        crowded = brief(override={"术语": "第 1 条：甲、乙、丙、丁\n第 2 条：戊"})
        code, res = self.run_cli(crowded, "--mode", "series", "--platform", "xhs")
        self.assertEqual(code, 0)
        self.assertTrue(any("第 1 条" in n for n in res["notices"]), res["notices"])

    def test_profile_feed_platforms_respected(self):
        text = brief(drop=["开头 3 秒"])
        code, r = self.run_cli(text, "--platform", "抖音", feed=("xhs",))
        self.assertEqual(code, 0, r)
        code, r = self.run_cli(text, "--platform", "抖音", feed=("douyin",))
        self.assertEqual(code, 1)

    def test_unknown_platform_notice(self):
        code, r = self.run_cli(brief(drop=["开头 3 秒"], override={"观看情境": "未定"}))
        self.assertEqual(code, 0, r)
        self.assertTrue(any("未识别平台" in n for n in r["notices"]))


if __name__ == '__main__':
    unittest.main()
