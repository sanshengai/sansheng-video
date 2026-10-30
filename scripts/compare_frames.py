#!/usr/bin/env python3
"""Prove that a revision left everything outside its scope unchanged.

Frame mode: OLD and NEW are check_timeline_seek.py output directories. Forward
screenshots are paired by sample time; outside the scope they must be
pixel-identical, inside the scope they are listed for viewing.

EDL mode: OLD and NEW are EDL JSON files. Every scene that does not touch the
scope must keep its timeline interval, source, source in/out points and, when
the source file exists next to the EDL, its sha256. Top-level audio fields
(audio_mode, audio_file and the audio file's sha256) must not change either.

Usage:
  python3 compare_frames.py OLD_QA_DIR NEW_QA_DIR --scope 3.2-5.0[,8-9] [--json]
  python3 compare_frames.py old.edl.json new.edl.json --scope 3.2-5.0 [--json]

Exit code 1 when anything outside the scope changed, 2 on unusable input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def parse_scope(text):
    ranges = []
    for part in str(text).split(","):
        part = part.strip()
        if not part:
            continue
        try:
            a, b = (float(x) for x in part.split("-", 1))
        except ValueError:
            raise ValueError(f"范围写法应为 开始-结束（秒）：{part}")
        if not a < b:
            raise ValueError(f"范围的开始须小于结束：{part}")
        ranges.append((a, b))
    if not ranges:
        raise ValueError("至少给一个范围")
    return ranges


def inside(t, scope):
    return any(a <= t <= b for a, b in scope)


def touches(start, end, scope):
    return any(start < b and a < end for a, b in scope)


def forward_frames(directory):
    report = Path(directory) / "seek-report.json"
    if not report.is_file():
        raise ValueError(f"{directory} 里没有 seek-report.json")
    data = json.loads(report.read_text())
    frames = {}
    for shot in data.get("screenshots", []):
        if shot.get("mode") == "forward":
            path = Path(shot["path"])
            if not path.is_absolute() and not path.exists():
                path = Path(directory) / path.name
            frames[round(float(shot["time"]), 6)] = path
    if not frames:
        raise ValueError(f"{report} 没有顺序截帧记录")
    return frames


def pixel_difference(old, new):
    """Return None when identical, otherwise a short description."""
    from PIL import Image, ImageChops
    with Image.open(old) as a, Image.open(new) as b:
        if a.size != b.size:
            return f"尺寸不同 {a.size} → {b.size}"
        a, b = a.convert("RGBA"), b.convert("RGBA")
        raw_a, raw_b = a.tobytes(), b.tobytes()
        if raw_a == raw_b:
            return None
        # RGBA getbbox() looks only at alpha; take the union over every band.
        boxes = [band.getbbox() for band in ImageChops.difference(a, b).split()]
        boxes = [x for x in boxes if x]
        box = (min(x[0] for x in boxes), min(x[1] for x in boxes),
               max(x[2] for x in boxes), max(x[3] for x in boxes))
        changed = sum(raw_a[i:i + 4] != raw_b[i:i + 4] for i in range(0, len(raw_a), 4))
        return f"{changed} 个像素不同，区域 {box}"


def compare_frames(old_dir, new_dir, scope):
    try:
        import PIL  # noqa: F401
    except ImportError:
        raise ValueError("逐像素比对需要 Pillow：python3 -m pip install Pillow")
    old, new = forward_frames(old_dir), forward_frames(new_dir)
    result = {"mode": "frames", "changed_outside": [], "in_scope": [], "unchanged": [], "missing": []}
    for t in sorted(set(old) | set(new)):
        if t not in old or t not in new:
            result["missing"].append({"time": t, "side": "old" if t not in old else "new"})
            continue
        if inside(t, scope):
            result["in_scope"].append({"time": t, "old": str(old[t]), "new": str(new[t])})
            continue
        diff = pixel_difference(old[t], new[t])
        if diff:
            result["changed_outside"].append({"time": t, "detail": diff, "old": str(old[t]), "new": str(new[t])})
        else:
            result["unchanged"].append(t)
    return result


SCENE_KEYS = ("timeline_start", "timeline_end", "source", "source_in", "source_out")


def file_sha(base, name):
    """源文件按 EDL 所在目录解析；不存在时返回 None（只比对路径与出入点）。"""
    path = Path(base) / str(name)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def load_edl(path):
    data = json.loads(Path(path).read_text())
    items = data.get("scenes") if isinstance(data, dict) else None
    if not isinstance(items, list) or not items:
        raise ValueError(f"{path} 不是含 scenes 的 EDL")
    base = Path(path).parent
    out = []
    for i, scene in enumerate(items):
        if not isinstance(scene, dict) or any(k not in scene for k in SCENE_KEYS):
            raise ValueError(f"{path} 第 {i + 1} 个 scene 缺少 {'/'.join(SCENE_KEYS)}")
        out.append({k: scene[k] for k in SCENE_KEYS}
                   | {"source_sha256": file_sha(base, scene["source"]), "n": scene.get("n", i + 1)})
    audio = {"audio_mode": data.get("audio_mode"), "audio_file": data.get("audio_file")}
    audio["audio_sha256"] = file_sha(base, audio["audio_file"]) if audio["audio_file"] else None
    return out, audio


def compare_edl(old_path, new_path, scope):
    (old, old_audio), (new, new_audio) = load_edl(old_path), load_edl(new_path)
    key = lambda s: tuple(s[k] for k in (*SCENE_KEYS, "source_sha256"))
    new_keys, old_keys = {key(s) for s in new}, {key(s) for s in old}
    result = {"mode": "edl", "changed_outside": [], "in_scope": [], "unchanged": [], "missing": []}
    for side, items, other in (("old", old, new_keys), ("new", new, old_keys)):
        for s in items:
            if touches(s["timeline_start"], s["timeline_end"], scope):
                if side == "new":
                    result["in_scope"].append(s)
                continue
            if key(s) in other:
                if side == "old":
                    result["unchanged"].append(s["n"])
            else:
                result["changed_outside"].append({"side": side, "scene": s})
    if old_audio != new_audio:
        result["changed_outside"].append({"audio": {"old": old_audio, "new": new_audio}})
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("old")
    ap.add_argument("new")
    ap.add_argument("--scope", required=True, help="修改范围（秒），如 3.2-5.0,8-9")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        scope = parse_scope(args.scope)
        if Path(args.old).is_dir() and Path(args.new).is_dir():
            result = compare_frames(args.old, args.new, scope)
        elif Path(args.old).is_file() and Path(args.new).is_file():
            result = compare_edl(args.old, args.new, scope)
        else:
            raise ValueError("OLD 和 NEW 须同为截帧目录或同为 EDL 文件")
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"无法比对：{exc}", file=sys.stderr)
        return 2
    failed = bool(result["changed_outside"] or result["missing"])
    result["scope"] = scope
    result["status"] = "changed_outside_scope" if failed else "outside_scope_unchanged"
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"范围：{args.scope}")
        for item in result["changed_outside"]:
            print(f"✗ 范围外有变化：{json.dumps(item, ensure_ascii=False)}")
        for item in result["missing"]:
            print(f"✗ 只有一侧有这一帧：{item['time']} 秒（缺 {item['side']}）")
        for item in result["in_scope"]:
            print(f"· 范围内，供查看：{json.dumps(item, ensure_ascii=False)}")
        print(f"范围外未变 {len(result['unchanged'])} 项")
        print("结论：范围外有变化" if failed else "结论：范围外没有变化")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
