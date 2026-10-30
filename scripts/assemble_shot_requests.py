"""Assemble structured shot requests from one shot table: film locks + per-shot content.

The output is plain request text for a chat/web generator; it does not call any service.
Changing a lock and re-running regenerates every request, so locks stay verbatim across shots.
Field order follows references/shot-request-template.md.
"""
from pathlib import Path
import argparse
import json

SHOT_FIELDS = ("id", "segment", "first_frame", "action", "camera", "ambient", "end_state",
               "ambience", "foley")
WINDOWS = ("0-3s", "3-7s", "7-10s")
MUSIC_NONE = "none (no background music; the score is added in post)"


def load(path):
    data = json.loads(Path(path).read_text())
    locks, segments, shots = data["locks"], data.get("segments", {}), data["shots"]
    seen = set()
    for shot in shots:
        missing = [k for k in SHOT_FIELDS if not shot.get(k)]
        if locks.get("native_music") and not shot.get("music_dynamic"):
            missing.append("music_dynamic")
        if missing:
            raise ValueError(f"{shot.get('id', '?')} 缺字段：{', '.join(missing)}")
        if shot["id"] in seen:
            raise ValueError(f"镜头编号重复：{shot['id']}")
        seen.add(shot["id"])
        if len(shot["action"]) != len(WINDOWS):
            raise ValueError(f"{shot['id']} 的 action 须为 {len(WINDOWS)} 段")
        world, music = resolve(shot, segments)
        if world not in locks["worlds"]:
            raise ValueError(f"{shot['id']} 引用了未定义的场景锁：{world}")
        if locks.get("native_music") and music not in locks.get("music", {}):
            raise ValueError(f"{shot['id']} 引用了未定义的音乐锁：{music}")
        for name in shot.get("characters", []):
            if name not in locks["characters"]:
                raise ValueError(f"{shot['id']} 引用了未定义的角色锁：{name}")
        for name in shot.get("refs", []):
            if name not in locks.get("refs", {}):
                raise ValueError(f"{shot['id']} 引用了未定义的参考图：{name}")
    return data


def resolve(shot, segments):
    seg = segments.get(shot["segment"], {})
    return (shot.get("world") or seg.get("world") or shot["segment"],
            shot.get("music") or seg.get("music") or shot["segment"])


def sentence(text):
    text = text.strip()
    return text if text[-1:] in ".!?" else text + "."


def cast_line(shot, locks):
    names = [locks.get("names", {}).get(c, c.upper()) for c in shot.get("characters", [])]
    extras = shot.get("extras", [])
    total = len(names) + len(extras)
    if total == 0:
        return "NO PEOPLE IN FRAME: landscape and objects only.", "No people in frame."
    who = ", ".join(names + extras)
    word = "CHARACTER" if total == 1 else "CHARACTERS"
    return (f"EXACTLY {total} {word}, NO DUPLICATES: {who}. No other people.",
            f"Exactly {total} {word.lower()} in frame: {who}.")


def request(shot, locks, segments, style="default"):
    world, music = resolve(shot, segments)
    cast, count = cast_line(shot, locks)
    refs = locks.get("refs", {})
    lines = [f"CAST: {cast}"]
    if shot.get("refs"):
        lines.append("REFERENCES: " + "; ".join(
            f"image {i} = {r} ({refs[r]['use']})" for i, r in enumerate(shot["refs"], 1)))
    lines.append(f"STYLE: {locks['style'][style]}")
    lines += [f"CHARACTER {locks.get('names', {}).get(c, c.upper())}: {locks['characters'][c]}"
              for c in shot.get("characters", [])]
    lines += [f"WORLD: {locks['worlds'][world]}", f"FORMAT: {locks['format']}",
              f"FIRST FRAME (0s): {shot['first_frame']}",
              "ACTION: " + " / ".join(f"{w} {a}" for w, a in zip(WINDOWS, shot["action"])),
              f"CAMERA: {shot['camera']}"]
    if shot.get("light"):
        lines.append(f"LIGHT: {shot['light']}")
    lines += [f"AMBIENT MOTION: {shot['ambient']}", f"END STATE (10s): {sentence(shot['end_state'])} {count}"]
    if shot.get("next"):
        lines.append(f"CUTS TO: {shot['next']}")
    if locks.get("native_music"):
        music_line = f"{locks['music'][music]}; {shot['music_dynamic']}"
    else:
        music_line = MUSIC_NONE
    lines += ["AUDIO:", f"  Ambience: {shot['ambience']}"]
    if shot["foley"] != "none":
        lines.append(f"  Foley: {shot['foley']}")
    lines += [f"  Music: {music_line}", f"  Voice: {locks['voice']}", f"  Mix: {locks['mix']}"]
    if shot.get("characters"):
        lines.append(f"CONTINUITY: {locks['continuity']}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("table")
    ap.add_argument("--out", required=True, help="输出目录；每个 batch 一个 txt")
    ap.add_argument("--shots", help="只拼这些镜头，逗号分隔，如 S13,S35")
    ap.add_argument("--style", default="default", help="locks.style 中的变体名")
    args = ap.parse_args()
    data = load(args.table)
    locks, segments = data["locks"], data.get("segments", {})
    if args.style not in locks["style"]:
        raise SystemExit(f"未定义的风格变体：{args.style}")
    wanted = set(args.shots.split(",")) if args.shots else None
    shots = [s for s in data["shots"] if wanted is None or s["id"] in wanted]
    if wanted and len(shots) != len(wanted):
        raise SystemExit(f"找不到镜头：{', '.join(sorted(wanted - {s['id'] for s in shots}))}")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    batches = {}
    for s in shots:
        key = "selected" if wanted else s.get("batch", "all")
        batches.setdefault(key, []).append(s)
    refs = locks.get("refs", {})
    for key, group in batches.items():
        used = list(dict.fromkeys(r for s in group for r in s.get("refs", [])))
        head = ""
        if used:
            head = "REFERENCES (attach in this order):\n" + "\n".join(
                f"- {r}: {refs[r]['file']} | {refs[r]['use']}" for r in used) + "\n\n"
        body = head + "\n\n".join(
            f"===== {s['id']} ({s.get('seconds', '?')}s)"
            + (f" refs: {', '.join(s['refs'])}" if s.get("refs") else "") + " =====\n"
            + request(s, locks, segments, args.style) for s in group)
        name = f"{key}-{args.style}.txt" if args.style != "default" else f"{key}.txt"
        (out / name).write_text(body + "\n")
    print(json.dumps({"shots": len(shots), "files": len(batches), "style": args.style}, ensure_ascii=False))


if __name__ == "__main__":
    main()
