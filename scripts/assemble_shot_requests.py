"""Assemble structured shot requests from one shot table: film locks + per-shot content.

Supports both legacy 15-block IR output (`profile="legacy"`, default) and
model-distilled profiles (`muse-i2v-still`, `muse-i2v-action`, `muse-t2v`, `grok-r2v`)
with optional `--lint` cross-field contradiction checking via `lint_video_prompt.py`.
"""
from __future__ import annotations

from pathlib import Path
import argparse
import json
import re
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lint_video_prompt import CAM_MOVE_RE, lint_shot_prompt, strip_negated_clauses

SHOT_FIELDS = ("id", "segment", "first_frame", "action", "camera", "ambient", "end_state",
               "ambience", "foley")
WINDOWS = ("0-3s", "3-7s", "7-10s")
MUSIC_NONE = "none (no background music; the score is added in post)"
PROFILES = ("legacy", "keyframe", "muse-i2v-still", "muse-i2v-action", "muse-i2v-continuous", "muse-t2v", "grok-r2v")
_GROK_SLOW_RE = re.compile(r"\bslow(?:ly|er|est|ing)?\b", re.I)
STYLE_KEYFRAME_ORDER = ("anchor", "light", "color", "texture", "composition", "mood")
STYLE_VIDEO_ORDER = ("anchor", "light", "color", "texture", "motion", "mood")


def format_style(style_entry, *, for_video: bool = False) -> str:
    """Render locks.style[name] from either a legacy string or a structured 5-decision dict.

    When `for_video=True`, static `composition` is stripped automatically so it never fights camera motion.
    """
    if isinstance(style_entry, str):
        return style_entry.strip()
    if not isinstance(style_entry, dict):
        raise ValueError(f"风格定义须为字符串或结构化对象：{style_entry!r}")
    order = STYLE_VIDEO_ORDER if for_video else STYLE_KEYFRAME_ORDER
    parts = [str(style_entry[k]).strip().rstrip(".,;") for k in order if str(style_entry.get(k, "")).strip()]
    return "; ".join(parts)


def load(path, profile="legacy"):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    locks, segments, shots = data["locks"], data.get("segments", {}), data["shots"]
    seen = set()
    if profile == "legacy":
        req_fields = SHOT_FIELDS
    elif profile == "keyframe":
        req_fields = ("id", "segment", "first_frame")
    else:
        req_fields = ("id", "segment", "camera", "ambient", "ambience")
    for shot in shots:
        missing = [k for k in req_fields if not shot.get(k)]
        if profile == "legacy":
            if locks.get("native_music") and not shot.get("music_dynamic"):
                missing.append("music_dynamic")
        elif profile not in ("muse-i2v-still", "muse-i2v-continuous", "keyframe") and not shot.get("action"):
            missing.append("action")
        if missing:
            raise ValueError(f"{shot.get('id', '?')} 缺字段：{', '.join(missing)}")
        if shot["id"] in seen:
            raise ValueError(f"镜头编号重复：{shot['id']}")
        seen.add(shot["id"])
        if profile == "legacy" and len(shot["action"]) != len(WINDOWS):
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


def _format_action_windows(shot):
    act = shot.get("action") or ""
    end_state = (shot.get("end_state") or "").strip().rstrip(".")
    if isinstance(act, str):
        main = act.strip().rstrip(".")
        tail = end_state or "holds the exact end pose and framing without new movement"
        return main, tail
    parts = [str(x).strip().rstrip(".") for x in act if str(x).strip()]
    if len(parts) == 1:
        main = parts[0]
        tail = end_state or "holds the exact end pose and framing without new movement"
    elif len(parts) == 2:
        main, tail = parts[0], end_state or parts[1]
    else:
        main = "; ".join(parts[:-1])
        tail = end_state or parts[-1]
    return main, tail


def _short_char_anchors(shot, locks):
    if shot.get("wide_or_back"):
        return ""
    char_map = locks.get("video_characters") or locks.get("characters") or {}
    items = []
    for c in shot.get("characters", []):
        cname = locks.get("names", {}).get(c, c.upper())
        desc = (char_map.get(c) or "").strip().rstrip(".")
        if desc:
            items.append(f"{cname} ({desc})")
    return "; ".join(items)


def _audio_line(shot):
    amb = (shot.get("ambience") or "quiet room tone").strip().rstrip(".")
    foley = (shot.get("foley") or "none").strip().rstrip(".")
    snd = f"{amb}; {foley}" if foley and foley.lower() != "none" else amb
    return f"Audio: {snd} only; no music, no speech, no human vocalizations."


def _guard_line(shot):
    base = "Single continuous shot with no cuts; no readable writing anywhere; held props stay in hand"
    extra = (shot.get("guard") or "").strip().rstrip(".")
    return f"Guard: {base}" + (f"; {extra}." if extra else ".")


def request(shot, locks, segments, style="default"):
    world, music = resolve(shot, segments)
    cast, count = cast_line(shot, locks)
    refs = locks.get("refs", {})
    lines = [f"CAST: {cast}"]
    if shot.get("refs"):
        lines.append("REFERENCES: " + "; ".join(
            f"image {i} = {r} ({refs[r]['use']})" for i, r in enumerate(shot["refs"], 1)))
    lines.append(f"STYLE: {format_style(locks['style'][style], for_video=False)}")
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


def compile_request(shot, locks, segments, style="default", profile="legacy"):
    """Compile an IR shot into a model-ready prompt according to `profile`."""
    if profile == "legacy":
        return request(shot, locks, segments, style=style)
    if profile not in PROFILES:
        raise ValueError(f"未知编译 profile：{profile}")

    world, _ = resolve(shot, segments)
    _, count_end = cast_line(shot, locks)
    char_anchors = _short_char_anchors(shot, locks)
    pos = (shot.get("spatial_anchor") or shot.get("first_frame") or "").strip().rstrip(".")

    if profile == "keyframe":
        style_txt = format_style(locks["style"][style], for_video=False)
        full_chars = []
        for c in shot.get("characters", []):
            cname = locks.get("names", {}).get(c, c.upper())
            desc = (locks.get("characters", {}).get(c) or "").strip().rstrip(".")
            if desc:
                full_chars.append(f"{cname}: {desc}")
        lines = [
            f"Scene: {sentence(shot['first_frame'])}",
            f"World: {sentence(locks['worlds'][world])}",
            f"Style: {sentence(style_txt)}",
        ]
        if shot.get("light"):
            lines.append(f"Light: {sentence(shot['light'])}")
        if shot.get("composition"):
            lines.append(f"Composition: {sentence(shot['composition'])}")
        if full_chars:
            lines.append("Characters: " + "; ".join(full_chars) + ".")
        extra_guard = (shot.get("guard") or "").strip().rstrip(".")
        guard_txt = "Single continuous scene from one camera; no text, captions, signs, logos or watermark"
        lines.append(f"Guard: {guard_txt}" + (f"; {extra_guard}." if extra_guard else "."))
        return "\n".join(line for line in lines if line.strip())

    if profile in ("muse-i2v-still", "muse-i2v-action", "muse-i2v-continuous"):
        cam_has_move = bool(CAM_MOVE_RE.search(strip_negated_clauses(shot.get("camera") or "")))
        if profile == "muse-i2v-continuous" or (profile == "muse-i2v-action" and cam_has_move):
            lock_head = "Exact start image as frame 1, keep scene, subjects and lighting consistent"
        else:
            lock_head = "Exact start image as frame 1, keep exact composition and lighting"
        lock_parts = [lock_head]
        if pos:
            lock_parts.append(pos)
        if char_anchors:
            lock_parts.append(char_anchors)
        lock_parts.append(count_end.rstrip("."))
        lines = [
            "Ref Lock: " + "; ".join(lock_parts) + ".",
            f"Camera: {sentence(shot['camera'])}",
        ]
        if profile == "muse-i2v-still":
            lines.append("Timeline: 0-10s all figures hold exact start poses with subtle breathing only, mouths closed.")
        elif profile == "muse-i2v-continuous":
            if shot.get("action"):
                main, _ = _format_action_windows(shot)
                lines.append(f"Timeline: 0-7s starting at frame 1, {main}, unfolding evenly through second 7.")
            else:
                lines.append("Timeline: 0-10s keep the scene and subjects consistent as the camera moves steadily.")
        else:
            main, tail = _format_action_windows(shot)
            lines.append(f"Timeline: 0-4s {main}; 4-10s {tail}.")
        lines.append(f"Ambient: {sentence(shot['ambient'])} Nothing else moves.")
        lines.append(_guard_line(shot))
        lines.append(_audio_line(shot))
        return "\n".join(lines)

    if profile == "muse-t2v":
        main, tail = _format_action_windows(shot)
        style_txt = format_style(locks["style"][style], for_video=True)
        lines = [
            f"Shot & Style: {sentence(style_txt)} {sentence(locks['worlds'][world])}",
            f"Scene: {sentence(shot.get('first_frame') or '')}" + (f" {char_anchors}." if char_anchors else ""),
            f"Camera: {sentence(shot['camera'])}",
            f"Timeline: 0-4s {main}; 4-10s {tail}.",
            f"Ambient: {sentence(shot['ambient'])}",
            _guard_line(shot),
            _audio_line(shot),
        ]
        return "\n".join(line for line in lines if line.strip())

    # grok-r2v
    main, tail = _format_action_windows(shot)
    for field_name, val in (("camera", shot["camera"]), ("action", main), ("end_state", tail)):
        if _GROK_SLOW_RE.search(val):
            raise ValueError(f"{shot['id']} grok-r2v 禁用 slow 类运动词（出现在 {field_name}）：{val!r}")
    cast, _ = cast_line(shot, locks)
    lines = [f"CAST: {cast}"]
    if shot.get("refs"):
        refs = locks.get("refs", {})
        lines.append("REFERENCES: " + "; ".join(
            f"image {i} = {r} ({refs[r]['use']})" for i, r in enumerate(shot["refs"], 1)))
    if char_anchors:
        lines.append(f"CHARACTERS: {char_anchors}.")
    lines.append(f"CAMERA: {sentence(shot['camera'])}")
    lines.append(f"ACTION: {main}. {tail}; hold expression and posture for ~1s after final word.")
    lines.append(f"AMBIENT: {sentence(shot['ambient'])}")
    dialogue = (shot.get("dialogue") or "").strip()
    amb = (shot.get("ambience") or "quiet room tone").strip().rstrip(".")
    foley = (shot.get("foley") or "none").strip().rstrip(".")
    audio_parts = [f"Ambience: {amb}"]
    if foley and foley.lower() != "none":
        audio_parts.append(f"Foley: {foley}")
    if dialogue:
        audio_parts.append(f"Dialogue: {dialogue}")
    else:
        audio_parts.append("Dialogue: none")
    audio_parts.append("Music: none")
    lines.append("AUDIO: " + "; ".join(audio_parts) + ".")
    return "\n".join(lines)


def _lint_mode_for(profile):
    return {
        "legacy": "legacy",
        "keyframe": "keyframe",
        "muse-i2v-still": "i2v-still",
        "muse-i2v-action": "i2v-action",
        "muse-i2v-continuous": "i2v-continuous",
        "muse-t2v": "t2v",
        "grok-r2v": "r2v-dialogue",
    }[profile]


def shot_dict_for_lint(shot, locks, segments, style="default", profile="legacy"):
    world, _ = resolve(shot, segments)
    main, tail = _format_action_windows(shot)
    compiled = compile_request(shot, locks, segments, style=style, profile=profile)
    start_txt = shot.get("first_frame") or ""
    if profile in ("legacy", "muse-t2v", "keyframe"):
        start_txt = f"{locks['worlds'][world]} {start_txt}".strip()
    if profile == "keyframe":
        return {
            "id": shot["id"],
            "raw_prompt": compiled,
            "start": start_txt,
            "light": shot.get("light") or "",
            "camera": shot.get("composition") or "",
            "guard": shot.get("guard") or "",
            "indoor": shot.get("indoor"),
            "no_speech": False,
        }
    return {
        "id": shot["id"],
        "raw_prompt": compiled,
        "start": start_txt,
        "light": shot.get("light") or (locks["worlds"][world] if profile == "muse-t2v" else ""),
        "camera": shot["camera"],
        "action": f"{main} {tail}".strip() if profile != "muse-i2v-still" else "hold exact start pose, mouths closed",
        "ambient": shot["ambient"],
        "guard": shot.get("guard") or "",
        "audio": _audio_line(shot) if profile != "grok-r2v" else (shot.get("ambience") or ""),
        "indoor": shot.get("indoor"),
        "no_speech": profile != "grok-r2v" or not bool((shot.get("dialogue") or "").strip()),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("table")
    ap.add_argument("--out", required=True, help="输出目录；每个 batch 一个 txt")
    ap.add_argument("--shots", help="只拼这些镜头，逗号分隔，如 S13,S35")
    ap.add_argument("--style", default="default", help="locks.style 中的变体名")
    ap.add_argument("--profile", default="legacy", choices=PROFILES, help="输出编译模式")
    ap.add_argument("--lint", action="store_true", help="拼装后运行跨字段矛盾校验，有 error 则退出码 1")
    args = ap.parse_args()
    data = load(args.table, profile=args.profile)
    locks, segments = data["locks"], data.get("segments", {})
    if args.style not in locks["style"]:
        raise SystemExit(f"未定义的风格变体：{args.style}")
    wanted = set(args.shots.split(",")) if args.shots else None
    shots = [s for s in data["shots"] if wanted is None or s["id"] in wanted]
    if wanted and len(shots) != len(wanted):
        raise SystemExit(f"找不到镜头：{', '.join(sorted(wanted - {s['id'] for s in shots}))}")
    lint_errors = []
    if args.lint:
        mode = _lint_mode_for(args.profile)
        for s in shots:
            issues = lint_shot_prompt(shot_dict_for_lint(s, locks, segments, args.style, args.profile), mode=mode)
            for issue in issues:
                if issue["severity"] == "error":
                    lint_errors.append(f"{s['id']} ({issue['code']}): {issue['message']}")
        if lint_errors:
            for err in lint_errors:
                print(f"[LINT ERROR] {err}", file=sys.stderr)
            raise SystemExit(1)

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
            + compile_request(s, locks, segments, args.style, profile=args.profile) for s in group)
        name = f"{key}-{args.style}.txt" if args.style != "default" else f"{key}.txt"
        (out / name).write_text(body + "\n", encoding="utf-8")
    print(json.dumps({"shots": len(shots), "files": len(batches), "style": args.style, "profile": args.profile}, ensure_ascii=False))


if __name__ == "__main__":
    main()
