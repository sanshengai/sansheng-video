#!/usr/bin/env python3
"""Connect explicitly selected, staged SFX cues to a HyperFrames root composition.

Default: read-only JSON report. --out writes a fragment; --apply replaces only
our marked block after validating the project lock, files and cue times.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
from html.parser import HTMLParser

BEGIN = "<!-- SFX-AUTO BEGIN -->"
END = "<!-- SFX-AUTO END -->"
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


def number(value, name, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} 必须是有限数值")
    if value < 0 or (positive and value == 0):
        raise ValueError(f"{name} 必须{'大于' if positive else '不小于'} 0")
    return float(value)


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def find_manifest(index, explicit=None):
    candidates = [Path(explicit)] if explicit else [index.parent / "assets.lock.json", index.parent.parent / "assets.lock.json"]
    for path in candidates:
        if path.is_file():
            return path.resolve()
    raise ValueError("缺 assets.lock.json：先 stage 选定素材；也可显式 --manifest 指定")


def clean_auto_block(text):
    if (text.count("<!-- SFX-AUTO BEGIN") != text.count(END) or text.count(END) > 1
            or (END in text and text.index(END) < text.index("<!-- SFX-AUTO BEGIN"))):
        raise ValueError("SFX-AUTO 标记不完整或重复，需先修复工程")
    text = re.sub(r"[ \t]*<!-- SFX-AUTO BEGIN.*?SFX-AUTO END -->[ \t]*(?:\r?\n)?", "", text, flags=re.S)
    # Prior versions also marked each generated tag. Keep hand-authored audio.
    return re.sub(r"[ \t]*<audio\b(?=[^>]*\bdata-sfx-auto=)[^>]*>\s*</audio>[ \t]*(?:\r?\n)?", "", text)


class Composition(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.offsets = [0]
        for line in text.splitlines(keepends=True):
            self.offsets.append(self.offsets[-1] + len(line))
        self.stack = []
        self.root = None
        self.close_at = None
        self.ids = set()
        self.tracks = set()
        self.feed(text)
        self.close()
        if self.root is None or self.close_at is None:
            raise ValueError("缺可闭合的根 data-composition-id 元素，拒绝向 body 外插音轨")
        self.duration = number(float(self.root.get("data-duration", "nan")), "根 composition duration", positive=True)

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if data.get("id"):
            self.ids.add(data["id"])
        track = data.get("data-track-index")
        if track is not None:
            try:
                self.tracks.add(int(track))
            except ValueError:
                raise ValueError("现有 data-track-index 必须为整数")
        is_root = "data-composition-id" in data and "data-composition-src" not in data
        if is_root:
            if self.root is not None:
                raise ValueError("一个入口只能有一个根 composition")
            self.root = data
        if tag not in VOID:
            self.stack.append((tag, is_root))

    def handle_startendtag(self, tag, attrs):
        if tag not in VOID:
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)
        else:
            self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack or self.stack[-1][0] != tag:
            raise ValueError(f"HTML 标签未配对：{tag}")
        _, root = self.stack.pop()
        if root:
            row, col = self.getpos()
            self.close_at = self.offsets[row - 1] + col


def probe_audio(path):
    try:
        proc = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", str(path)], capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"无法探测音效：{path.name}: {exc}") from exc
    if proc.returncode != 0:
        raise ValueError(f"音效探测失败：{path.name}")
    data = json.loads(proc.stdout)
    if not any(s.get("codec_type") == "audio" for s in data.get("streams", [])):
        raise ValueError(f"文件没有音频流：{path.name}")
    return number(float(data.get("format", {}).get("duration", "nan")), "音效时长", positive=True)


def selected_cues(items, cue_path=None):
    pairs = []
    if cue_path:
        cues = read_json(Path(cue_path))
        if not isinstance(cues, list):
            raise ValueError("--cues 须为 cue 数组")
        for cue in cues:
            if not isinstance(cue, dict) or not cue.get("asset_id"):
                raise ValueError("外部 cue 缺 asset_id")
            matches = [item for item in items if item.get("id") == cue["asset_id"]
                       and ("revision" not in cue or item.get("revision") == cue["revision"])
                       and ("scene_id" not in cue or item.get("scene_id") == cue["scene_id"])]
            if len(matches) != 1:
                raise ValueError(f"cue 必须唯一匹配已 stage 条目：{cue['asset_id']}（可补 revision/scene_id）")
            pairs.append((matches[0], cue))
    else:
        for item in items:
            cues = item.get("cues", [])
            if not isinstance(cues, list):
                raise ValueError("锁定条目的 cues 须为数组")
            pairs.extend((item, cue) for cue in cues)
    if not pairs:
        raise ValueError("没有显式音效 cue；按内容选定并 stage 后再接线")
    return pairs


def plan(index, manifest, cue_path=None):
    raw = index.read_bytes().decode("utf-8")
    clean = clean_auto_block(raw)
    comp = Composition(clean)
    lock = read_json(manifest)
    items = lock.get("items") if isinstance(lock, dict) else None
    if not isinstance(items, list) or not items or any(not isinstance(x, dict) for x in items):
        raise ValueError("assets.lock.json 的 items 必须是非空对象数组")
    root = manifest.parent.resolve()
    if not index.is_relative_to(root):
        raise ValueError("index 必须位于清单所属工程内")
    events, seen_ids, seen_events, durations = [], set(), set(), {}
    first_track = max(comp.tracks, default=-1) + 1
    for item, cue in selected_cues(items, cue_path):
        if not isinstance(cue, dict):
            raise ValueError("cue 必须为对象")
        for key in ("id", "revision", "sha256", "project_path", "scene_id"):
            if not isinstance(item.get(key), str) or not item[key]:
                raise ValueError(f"锁定素材缺 {key}")
        rel = PurePosixPath(item["project_path"])
        if rel.is_absolute() or ".." in rel.parts or "\\" in item["project_path"] or re.match(r"^[A-Za-z]:", item["project_path"]):
            raise ValueError("project_path 越界或格式不合法")
        target = (root / item["project_path"]).resolve()
        if not target.is_relative_to(root) or not target.is_relative_to(index.parent):
            raise ValueError("素材路径或 symlink 超出工程 HTML 可引用目录")
        if not target.is_file() or target.stat().st_size == 0:
            raise ValueError(f"已采用音效缺文件或为空：{item['project_path']}")
        expected = item["sha256"]
        if not re.fullmatch(r"[0-9a-f]{64}", expected) or digest(target) != expected:
            raise ValueError(f"已采用音效哈希不符：{item['id']}")
        if target not in durations:
            durations[target] = probe_audio(target)
        start = number(cue.get("time"), "cue.time")
        length = number(cue.get("duration", durations[target]), "cue.duration", positive=True)
        if length > durations[target] + 0.001 or start + length > comp.duration + 0.001:
            raise ValueError("cue 时段超出音效原件或根 composition 时长")
        volume = number(cue.get("volume", 0.45), "cue.volume")
        track = cue.get("track", first_track + len(events))
        if isinstance(track, bool) or not isinstance(track, int) or track < 0:
            raise ValueError("cue.track 须为非负整数")
        if track in comp.tracks:
            raise ValueError("cue.track 已被手工轨道占用；省略 track 可自动分配")
        identity = (item["id"], item["revision"], item["scene_id"], start)
        cue_id = cue.get("id", "sfx-" + hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:16])
        if not isinstance(cue_id, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]*", cue_id):
            raise ValueError("cue.id 必须是安全的 HTML id")
        if cue_id in seen_ids or cue_id in comp.ids or identity in seen_events:
            raise ValueError("重复音效 cue 或 HTML id")
        if any(e["track"] == track and start < e["time"] + e["duration"] and e["time"] < start + length for e in events):
            raise ValueError("同一音轨的 cue 时段重叠")
        seen_ids.add(cue_id)
        seen_events.add(identity)
        events.append(dict(id=cue_id, asset_id=item["id"], revision=item["revision"], scene_id=item["scene_id"], src=target.relative_to(index.parent).as_posix(), time=start, duration=length, volume=volume, track=track))
    events.sort(key=lambda e: (e["time"], e["id"]))
    tags = [BEGIN]
    for e in events:
        attrs = {"id": e["id"], "data-sfx-auto": "1", "data-asset-id": e["asset_id"], "data-asset-revision": e["revision"], "data-scene-id": e["scene_id"], "src": e["src"], "data-start": f"{e['time']:.6f}".rstrip("0").rstrip("."), "data-duration": f"{e['duration']:.6f}".rstrip("0").rstrip("."), "data-volume": str(e["volume"]), "data-track-index": str(e["track"])}
        tags.append("<audio " + " ".join(f'{k}="{html.escape(v, quote=True)}"' for k, v in attrs.items()) + "></audio>")
    tags.append(END)
    fragment = "\n".join(tags) + "\n"
    insert_at = comp.close_at
    line_start = clean.rfind("\n", 0, insert_at) + 1
    if not clean[line_start:insert_at].strip():
        insert_at = line_start
    updated = clean[:insert_at] + fragment + clean[insert_at:]
    return raw, updated, fragment, events


def atomic_write(path, text):
    fd, tmp = tempfile.mkstemp(prefix=".sfx-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
        if path.exists():
            os.chmod(tmp, path.stat().st_mode & 0o777)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--cues", type=Path, help="显式 cue JSON 数组；time 为全片绝对秒")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("-o", "--out", type=Path, help="只在显式指定时写新片段文件")
    args = parser.parse_args(argv)
    try:
        index = args.index.resolve(strict=True)
        manifest = find_manifest(index, args.manifest)
        raw, updated, fragment, events = plan(index, manifest, args.cues)
        if args.out:
            with args.out.open("x", encoding="utf-8") as stream:
                stream.write(fragment)
        changed = updated != raw
        if args.apply and changed:
            if index.read_bytes().decode("utf-8") != raw:
                raise ValueError("工程已被其他操作修改，请重新规划")
            backup = index.with_name(index.name + ".sfx-" + hashlib.sha256(raw.encode()).hexdigest()[:16] + ".bak")
            if backup.exists() and backup.read_bytes().decode("utf-8") != raw:
                raise ValueError("备份名冲突，拒绝覆盖")
            if not backup.exists():
                with backup.open("x", encoding="utf-8", newline="") as stream:
                    stream.write(raw)
            atomic_write(index, updated)
        print(json.dumps({"mode": "apply" if args.apply else "dry-run", "changed": changed if args.apply else False, "manifest": str(manifest), "events": events}, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"SFX 接线失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
