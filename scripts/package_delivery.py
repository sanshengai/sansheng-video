#!/usr/bin/env python3
"""Create a shallow, independently usable local delivery. Never uploads."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.parse import quote, urlparse


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def copy_subtitles(spec, source_root, staging):
    """Copy explicitly selected sidecars; never infer a subtitle from nearby files."""
    rows = spec.get('subtitles', [])
    if not isinstance(rows, list):
        raise ValueError('subtitles must be a list')
    result, hashes, seen = [], {}, set()
    for row in rows:
        language = row.get('language','') if isinstance(row,dict) else ''
        if not re.fullmatch(r'[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8})*', language) or language.lower() in seen:
            raise ValueError('subtitle requires a unique language')
        seen.add(language.lower())
        if not isinstance(row.get('path'),str) or not row['path']:
            raise ValueError('subtitle path required')
        source = (Path(source_root)/row['path']).resolve()
        if not source.is_file() or source.suffix.lower() not in {'.srt','.vtt'} or not source.stat().st_size:
            raise ValueError('subtitle must be a nonempty SRT or VTT file')
        original = digest(source)
        name = f'subtitles-{language}{source.suffix.lower()}'
        shutil.copy2(source, Path(staging)/name)
        if digest(Path(staging)/name) != original or digest(source) != original:
            raise ValueError('subtitle changed during copy')
        result.append(dict(path=name,language=language))
        hashes[name] = original
    return result, hashes


def probe(video):
    info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                                      "-of", "json", str(video)], capture_output=True, text=True,
                                     check=True, timeout=60).stdout)
    streams = info.get("streams", [])
    videos = [s for s in streams if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")]
    if len(videos) != 1:
        raise ValueError("delivery needs one video stream")
    video_stream = videos[0]
    duration = float(info["format"]["duration"])
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("invalid video duration")
    numerator, denominator = map(int, video_stream["avg_frame_rate"].split("/"))
    if not denominator or numerator <= 0:
        raise ValueError("invalid video frame rate")
    return {"width": video_stream["width"], "height": video_stream["height"],
            "duration": duration, "fps": numerator / denominator,
            "video_codec": video_stream["codec_name"],
            "audio_codecs": [s["codec_name"] for s in streams if s.get("codec_type") == "audio"]}


def package(source, destination):
    source, destination = Path(source).resolve(), Path(destination).absolute()
    spec = json.loads(source.read_text())
    for key in ("title", "summary", "suggested_title", "project", "filename"):
        if not isinstance(spec.get(key), str) or not spec[key].strip():
            raise ValueError(f"{key}: nonempty text required")
    name = spec["filename"]
    if Path(name).name != name or any(c in name for c in ("/", "\\", "\0", "\n", "\r")) or not name.lower().endswith(".mp4"):
        raise ValueError("filename must be a plain MP4 filename")
    if spec.get("review_status") not in {"candidate", "user_accepted"}:
        raise ValueError("declare review_status: candidate or user_accepted")
    if spec["review_status"] == "user_accepted" and not spec.get("review_source"):
        raise ValueError("user acceptance requires original feedback/version reference")
    video = (source.parent / spec["video"]).resolve()
    if video.suffix.lower() != ".mp4" or not video.is_file():
        raise ValueError("video must be an existing MP4")
    if destination.is_symlink():
        raise ValueError("delivery destination cannot be a symlink")
    # Canonicalize the parent (macOS /var itself is a symlink), then publish here.
    destination = destination.parent.resolve() / destination.name
    if video.is_relative_to(destination.resolve()):
        raise ValueError("source video cannot be inside delivery directory")
    urls = spec.get("online_urls", [])
    if not isinstance(urls, list):
        raise ValueError("online_urls must be a list")
    for value in urls:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("invalid online URL")
    original = digest(video)
    info = probe(video)
    decode = subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(video), "-map", "0:v:0",
                             "-map", "0:a?", "-f", "null", "-"], capture_output=True, text=True,
                            timeout=max(60, info["duration"] * 10))
    if decode.returncode or decode.stderr.strip():
        raise ValueError("full decode failed: " + decode.stderr[-500:])
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".delivery-", dir=destination.parent) as temporary:
        staging = Path(temporary) / "package"
        staging.mkdir()
        shutil.copy2(video, staging / name)
        if digest(staging / name) != original or digest(video) != original:
            raise ValueError("video changed during delivery copy")
        poster = staging / "cover.jpg"
        if spec.get("poster"):
            poster_source = (source.parent / spec["poster"]).resolve()
            if poster_source.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                raise ValueError("poster must be JPG, PNG or WebP")
            poster = staging / ("cover" + poster_source.suffix.lower())
            shutil.copy2(poster_source, poster)
            if digest(poster) != digest(poster_source):
                raise ValueError("poster changed during copy")
        else:
            subprocess.run(["ffmpeg", "-v", "error", "-ss", str(info["duration"] * .35), "-i", str(video),
                            "-frames:v", "1", "-vf", "scale=960:960:force_original_aspect_ratio=decrease",
                            str(poster)], check=True, capture_output=True, timeout=60)
        subtitles, subtitle_hashes = copy_subtitles(spec, source.parent, staging)
        report = {"kind": "video-delivery/1", "source": str(video), "source_sha256": original,
                  "project": spec["project"], "title": spec["title"], "summary": spec["summary"],
                  "suggested_title": spec["suggested_title"], "review_status": spec["review_status"],
                  "review_source": spec.get("review_source"), "online_urls": urls,
                  "technical": {**info, "full_decode": True}, "video": name, "poster": poster.name,
                  "files": {name: original, poster.name: digest(poster)}}
        if subtitles:
            report['subtitles'] = subtitles
            report['files'].update(subtitle_hashes)
        (staging / "delivery.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        online = "\n".join(urls) or "无线上地址（尚未上传）"
        (staging / "说明.md").write_text(
            f"# {spec['title']}\n\n{spec['summary']}\n\n建议标题：{spec['suggested_title']}\n\n"
            f"成片：{destination / name}\n\n工程：{spec['project']}\n\n"
            f"规格：{info['width']}×{info['height']} · {info['duration']:.2f} 秒 · {info['fps']:g} fps\n\n"
            f"状态：{spec['review_status']}（技术检查不代表审美或平台上传通过）\n\n"
            f"线上地址：\n{online}\n\n文章放置参考：{spec.get('article_placement', '由文章作者根据内容决定')}\n")
        (staging / "preview.html").write_text(
            '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
            f'<title>{html.escape(spec["title"])}</title><body style="background:#161819;color:white;font-family:system-ui">'
            f'<h1>{html.escape(spec["title"])}</h1><video controls preload="metadata" style="max-width:100%;max-height:80vh" '
            f'src="{quote(name)}" poster="{poster.name}"></video><p>{html.escape(spec["summary"])}</p>')
        if destination.exists():
            expected = {p.name: digest(p) for p in staging.iterdir()}
            actual = {p.name: digest(p) for p in destination.iterdir() if p.is_file() and not p.is_symlink()}
            if expected != actual or len(list(destination.iterdir())) != len(expected):
                raise ValueError("delivery exists with different content; choose a new version/directory")
        else:
            staging.rename(destination)
    return {"directory": str(destination), "video": str(destination / name), "sha256": original,
            "review_status": spec["review_status"], "uploaded": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(json.dumps(package(args.spec, args.destination), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
