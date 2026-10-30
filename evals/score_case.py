#!/usr/bin/env python3
"""Score one planning-stage eval case. Prints JSON; exit 0 only when every check passes.

Usage: python3 evals/score_case.py CASE_ID OUTPUT_DIR
"""
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
sys.path.insert(0, str(SKILL / "scripts"))
import production_timeline  # noqa: E402


def run(*args):
    proc = subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True)
    return proc.returncode, proc.stdout


def section(text, title):
    m = re.search(rf"^##\s*{re.escape(title)}\s*$(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    return m.group(1).strip() if m else ""


def valid_timeline(path):
    try:
        data = json.loads(path.read_text())
        production_timeline.products(data)
        return True, data
    except Exception as exc:  # noqa: BLE001 - the error text is the evidence
        return False, str(exc)


def brief_checks(out, mode, platform):
    brief = out / "brief.md"
    checks = {"brief.md 存在": brief.is_file()}
    if not brief.is_file():
        return checks, ""
    code, _ = run(SKILL / "scripts/check_brief.py", brief, "--mode", mode, "--platform", platform,
                  "--profile-dir", HERE / "fixtures")
    checks[f"check_brief --mode {mode} 通过"] = code == 0
    return checks, brief.read_text()


def readability_handled(timeline, brief_text):
    code, stdout = run(SKILL / "scripts/check_readability.py", timeline, "--json",
                       "--profile-dir", HERE / "fixtures")
    count = json.loads(stdout)["count"] if code == 0 else -1
    return count == 0 or bool(section(brief_text, "自主决定"))


def score(case, out):
    checks = {}
    if case == "article-to-feed":
        c, text = brief_checks(out, "new", "douyin")
        checks.update(c)
        checks["开头 3 秒已写且未豁免"] = bool(text) and not section(text, "开头 3 秒").startswith("豁免")
        ok, data = valid_timeline(out / "timeline.json")
        checks["timeline.json 通过时间线校验"] = ok
        if ok:
            w, h = data["canvas"]
            checks["竖屏画布"] = h > w
            checks["时长 25–35 秒"] = 25 <= data["duration"] <= 35
            checks["可读性提示已处理或写了理由"] = readability_handled(out / "timeline.json", text)
    elif case == "promo-series":
        c, text = brief_checks(out, "series", "xhs")
        checks.update(c)
        scope = section(text, "系列范围")
        checks["系列范围列出 3 条"] = all(k in scope for k in ("离线", "语音", "模板"))
        approved = section(text, "已认可组合")
        checks["已认可组合沿用样板"] = all(k in approved for k in ("96", "calm-piano-v2"))
        ok, _ = valid_timeline(out / "timeline-1.json")
        checks["timeline-1.json 通过时间线校验"] = ok
    elif case == "local-caption-fix":
        card = out / "revision-card.md"
        text = card.read_text() if card.is_file() else ""
        checks["修订卡存在且有范围、必须不变、证明"] = all(k in text for k in ("范围", "必须不变", "证明"))
        checks["没有另写新制作单"] = not (out / "brief.md").exists()
        ok, data = valid_timeline(out / "timeline.json")
        checks["timeline.json 通过时间线校验"] = ok
        if ok:
            expected = json.loads((HERE / "fixtures/local-edit-timeline.json").read_text())
            for event in expected["events"]:
                if event["id"] == "cap-compare":
                    event["caption"] = "要求越模糊，结果越难用"
            checks["只改了那一句字幕"] = data == expected
    else:
        raise SystemExit(f"unknown case {case}")
    return checks


def main():
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    checks = score(sys.argv[1], Path(sys.argv[2]))
    passed = all(checks.values())
    print(json.dumps({"case": sys.argv[1], "passed": passed, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
