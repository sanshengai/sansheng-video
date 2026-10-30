#!/usr/bin/env python3
"""检查制作单 brief.md 的必填标题是否齐全（只查有没有，不评好坏）。

判据来源：references/brief-template.md 的「标题与必填」表。
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

COMMON = ["一句话主张", "观看情境", "术语", "段落表"]
FILM_LINE = re.compile(r"^\s*(?:[-*+]\s*)?第\s*(\d+)\s*条\s*[:：]\s*(.*)$")
REQUIRED = {
    "new": COMMON + ["结构候选", "视觉母题与强调色"],
    "continue": COMMON + ["已认可组合"],
    "series": COMMON + ["已认可组合", "系列范围"],
}
HOOK = "开头3秒"
DEFAULT_FEED = ["douyin", "shipinhao", "xhs", "tiktok", "reels", "shorts"]
# 平台别名 -> 代码（比较时小写）
ALIASES = [
    ("抖音", "douyin"), ("douyin", "douyin"),
    ("视频号", "shipinhao"), ("shipinhao", "shipinhao"),
    ("小红书", "xhs"), ("xhs", "xhs"),
    ("tiktok", "tiktok"), ("reels", "reels"), ("shorts", "shorts"),
    ("哔哩哔哩", "bilibili"), ("b站", "bilibili"), ("bilibili", "bilibili"),
    ("youtube", "youtube"),
]
MODES = tuple(REQUIRED)


def _norm(s):
    return re.sub(r"\s+", "", s)


def parse_sections(text):
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    sections = {}
    cur = None
    for line in text.splitlines():
        m = re.match(r"^##(?!#)\s*(.*?)\s*$", line)
        if m:
            cur = _norm(m.group(1))
            sections.setdefault(cur, [])
        elif cur is not None:
            sections[cur].append(line)
    return {k: "\n".join(v).strip() for k, v in sections.items()}


def is_empty(body):
    lines = [l.strip() for l in body.splitlines() if l.strip()]
    if not lines:
        return True
    if all(l.startswith("|") for l in lines):
        data = []
        for i, l in enumerate(lines):
            if i == 0:
                continue  # 表头
            cells = [c.strip() for c in l.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c) or c == "" for c in cells):
                continue  # 分隔行或全空行
            data.append(l)
        return not data
    return False


def canon_platform(name):
    if not name:
        return None
    low = name.strip().lower()
    for alias, code in ALIASES:
        if alias in low:
            return code
    return low or None


def detect_platforms(body):
    low = body.lower()
    found = []
    for alias, code in ALIASES:
        if alias in low and code not in found:
            found.append(code)
    return found


def load_feed_platforms(profile_dir):
    """返回 (清单, 提示)。优先 profile，其次默认清单。"""
    notices = []
    try:
        sys.path.insert(0, str(ROOT))
        from setup import profile
        data = profile(profile_dir)
        feed = ((data or {}).get("configuration", {}).get("delivery") or {}).get("feed_platforms")
        if isinstance(feed, list) and feed:
            return [str(x).lower() for x in feed], notices
    except Exception as exc:  # profile 坏了不应让检查崩溃
        notices.append("读取 profile 失败，改用默认信息流平台清单：%s" % exc)
    return list(DEFAULT_FEED), notices


def check_text(text, mode="new", platform=None, profile_dir=None):
    sections = parse_sections(text)
    missing, notices = [], []
    for title in REQUIRED[mode]:
        body = sections.get(_norm(title))
        if body is None:
            missing.append("缺标题：%s" % title)
        elif is_empty(body):
            missing.append("内容为空：%s" % title)

    feed, extra = load_feed_platforms(profile_dir)
    notices.extend(extra)
    plat = canon_platform(platform)
    if plat is None:
        found = detect_platforms(sections.get(_norm("观看情境"), ""))
        feeds = [p for p in found if p in feed]
        plat = feeds[0] if feeds else (found[0] if found else None)
    if plat is None:
        notices.append("未识别平台，未检查开头 3 秒")
    elif plat in feed:
        body = sections.get(HOOK)
        if body is None:
            missing.append("缺标题：开头 3 秒（平台 %s 为竖屏信息流，必填；不适用请写「豁免：理由」）" % plat)
        elif is_empty(body):
            missing.append("内容为空：开头 3 秒")
        else:
            m = re.match(r"^豁免[：:](.*)$", body.strip(), flags=re.S)
            if m and not _norm(m.group(1)):
                missing.append("开头 3 秒：豁免必须写理由")

    terms = sections.get("术语")
    if terms and not is_empty(terms) and _norm(terms) != "无":
        films = [m for m in (FILM_LINE.match(line) for line in terms.splitlines()) if m]
        groups = [(f"第 {m.group(1)} 条", m.group(2)) for m in films] if films else [("", terms)]
        for label, body in groups:
            items = [t for t in re.split(r"[,，、\n]", body) if re.sub(r"^[\s\-*+•\d.、)]+", "", t).strip()]
            if len(items) > 3:
                notices.append("%s术语共 %d 个，模板建议每条 1–3 个" % (label, len(items)))
    return {"missing": missing, "notices": notices, "mode": mode, "platform": plat}


def main(argv=None):
    ap = argparse.ArgumentParser(description="检查制作单必填项")
    ap.add_argument("brief")
    ap.add_argument("--mode", choices=MODES, default="new")
    ap.add_argument("--platform")
    ap.add_argument("--profile-dir")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        text = Path(args.brief).read_text(encoding="utf-8")
    except OSError as exc:
        print("无法读取制作单：%s" % exc)
        return 2
    r = check_text(text, args.mode, args.platform, args.profile_dir)
    if args.json:
        print(json.dumps(r, ensure_ascii=False))
    else:
        for m in r["missing"]:
            print("缺：" + m)
        for n in r["notices"]:
            print("提示：" + n)
        print("结论：未通过，缺 %d 项" % len(r["missing"]) if r["missing"]
              else "结论：通过（模式 %s）" % args.mode)
    return 1 if r["missing"] else 0


if __name__ == "__main__":
    sys.exit(main())
