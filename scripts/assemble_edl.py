#!/usr/bin/env python3
# sansheng-video — EDL 分段装配，保留原三阶段结构：抽段 → concat → 成片音轨。
#
# 来源：guigulaoshi/music-video-director-skill / mvd/renderer.py、mvd/validate.py
# https://github.com/guigulaoshi/music-video-director-skill
# License: MIT；首次移植 2026-05-30
# 锁定上游：06abf674e936eefd69f053759f673e3c72f71e2e
# 本地扩展（2026-10-15）：显式音频意图、画幅、真实流与成片检查；不是上游原样实现。
#
# external：--audio 或 EDL.audio_file 是明确的替换原声请求，不混轨。
#           兼容旧调用默认 1080x1920；--width/--height 可覆盖。
# source：逐段保留原声，PCM 中间件避免逐段 AAC priming；最后只编码一次 AAC。
# silent：明确不含音轨。source/silent 未指定画幅时继承一致的源尺寸。
# source/silent 与外置音轨声明冲突时拒绝，不猜优先级。
#
# 外置音轨时长容差=max(1/fps,1024/48000)+1e-6 秒，只容纳帧/AAC rounding。
# 不使用 -shortest，不填静音或循环音轨。原声缺失/覆盖不足、非零流起点、
# 多流选择歧义、混合声道或隐式环绕声降混均拒绝，需上游明确处理。
# 输出实际核验尺寸/FPS/帧数/视频音频与容器时长、完整解码，通过后无覆盖发布。
# 仍沿用 validate_edl 的同源倒序/重复/重叠/head-buffer 限制，不扩展编辑语义。
# --no-validate 仅兼容旧结构检查开关，新增真实媒体检查始终执行。
#
# EDL 是本地 scenes/source/source_in/source_out/timeline_start/timeline_end JSON，
# 兼容 cuts/source_file 别名；不是业界 CMX3600 文本，不可直接交给 DaVinci import。
# metadata.total_duration 为编辑总时长；audio_file 可被 --audio 覆盖。
# 例：assemble_edl.py edl.json --audio-mode source --out edited.mp4
#     assemble_edl.py edl.json --audio-mode silent --width 1280 --height 720 --out mute.mp4
#     assemble_edl.py edl.json --audio narration.wav --out narrated.mp4

from __future__ import annotations

import argparse
import json
import math
from fractions import Fraction
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

# ----- 旧 external 模式的兼容默认 -------------------------------------------------
TARGET_WIDTH = 1080         # 9:16 竖屏标准短边（抖音/视频号/小红书竖版基准宽）
TARGET_HEIGHT = 1920        # 9:16 竖屏标准长边（1080x1920 = 抖音/视频号/小红书竖版成片规格）
DEFAULT_FPS = 30.0          # 对齐 hyperframes npm run render --fps 30
HEAD_BUFFER_FRAMES = 3      # 防闪帧：source_in 多留 3 帧 head buffer，硬截帧时丢掉
PAD_COLOR = "black"
# -----------------------------------------------------------------------------


def _get_scenes(edl: dict) -> list:
    """读 scene 序列。原生键 "scenes"，兼容上游别名 "cuts"。"""
    return edl.get("scenes") or edl.get("cuts") or []


def _scene_source(scene: dict) -> str:
    """读分段文件路径。原生键 "source"，兼容上游别名 "source_file"。"""
    return scene.get("source") or scene["source_file"]


# =============================================================================
# 校验闸门：先调 validate_edl 通过才拼接
# =============================================================================
def _gate_validate(edl: dict, edl_path: str, audio_duration: Optional[float], fps: float) -> None:
    """
    先调 sansheng-video 同目录 validate_edl.py 的 assert_valid_edl() 把关，
    校验不过直接退出，绝不带病拼接。

    若 validate_edl.py 尚未就位（旧仓 / 单测环境），退化为内联最小校验
    （source_out > source_in、文件存在），保证脚本仍可独立跑通。
    """
    # 优先用 sibling validate_edl 模块（与本脚本同一份 EDL schema）
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from validate_edl import assert_valid_edl  # type: ignore
    except Exception:
        assert_valid_edl = None  # type: ignore

    if assert_valid_edl is not None:
        # sansheng-video 原生 validate_edl.assert_valid_edl 形参用 total_duration / fps；
        # 用 try 阶梯兼容（兼上游 audio_duration 形参的可能），不锁死单一签名。
        # 装配是「走多段拼接装配」权威路径：require_coverage / require_source_exists / edl_path
        # 全开 → total_duration 缺、source 实体文件缺都判 fail（不再静默全绿放行带病拼接）。
        for kwargs in (
            {"total_duration": audio_duration, "fps": fps, "edl_path": edl_path,
             "require_coverage": True, "require_source_exists": True},
            {"total_duration": audio_duration, "fps": fps},
            {"total_duration": audio_duration},
            {"audio_duration": audio_duration, "fps": fps},
            {},
        ):
            try:
                assert_valid_edl(edl, **kwargs)
                print("[validate] EDL 校验通过（validate_edl.assert_valid_edl）")
                return
            except AssertionError as e:
                print("[validate] EDL 校验未通过，停止拼接：\n" + str(e), file=sys.stderr)
                sys.exit(2)
            except TypeError:
                continue  # 形参不匹配，换下一组 kwargs 重试
        # 所有签名都不匹配，退化到内联校验
        print("[validate] validate_edl 签名不兼容，退化为内联最小校验")

    # ---- 退化：内联最小校验 ----
    print("[validate] 未找到 validate_edl.py，退化为内联最小校验")
    errors: list[str] = []
    scenes = _get_scenes(edl)
    if not scenes:
        errors.append("EDL 没有 scenes")
    for i, scene in enumerate(scenes):
        idx = scene.get("n", i + 1)
        has_source = ("source" in scene) or ("source_file" in scene)
        if not has_source:
            errors.append(f"scene #{idx} 缺字段 source")
        for key in ("source_in", "source_out"):
            if key not in scene:
                errors.append(f"scene #{idx} 缺字段 {key!r}")
        if "source_in" in scene and "source_out" in scene:
            si, so = float(scene["source_in"]), float(scene["source_out"])
            if so <= si:
                errors.append(f"scene #{idx}: source_out={so:.3f} <= source_in={si:.3f}")
        if has_source:
            src = _scene_source(scene)
            if not os.path.exists(_resolve(src, edl_path)):
                errors.append(f"scene #{idx}: 分段文件不存在 {src!r}")
    if errors:
        print("[validate] 内联校验未通过，停止拼接：", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(2)
    print("[validate] 内联最小校验通过")


def _resolve(path: str, edl_path: str) -> str:
    """相对路径按 EDL 文件所在目录解析，绝对路径原样返回。"""
    p = Path(path)
    if p.is_absolute():
        return str(p)
    return str((Path(edl_path).resolve().parent / p))


# =============================================================================
# 三段式确定性拼接管线（忠实移植 mvd/renderer.py）
# =============================================================================
def _run(command):
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise ValueError("media command failed: " + result.stderr[-2000:])
    return result.stdout


def _probe(path, count_frames=False):
    command = ["ffprobe", "-v", "error"]
    if count_frames:
        command += ["-count_frames"]
    return json.loads(_run(command + ["-show_streams", "-show_format", "-of", "json", str(path)]))


def _duration(stream):
    """Read this stream's duration, never substitute another stream's container length."""
    value = stream.get("duration")
    if value in (None, "N/A"):
        value = stream.get("tags", {}).get("DURATION")
        if value and ":" in value:
            h, m, seconds = value.split(":")
            value = int(h) * 3600 + int(m) * 60 + float(seconds)
    try:
        duration = float(value)
    except (ValueError, TypeError):
        raise ValueError("cannot establish actual stream duration")
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("invalid stream duration")
    return duration


def _streams(probe, kind):
    return [s for s in probe.get("streams", []) if s["codec_type"] == kind]


def _one_stream(probe, kind):
    streams = _streams(probe, kind)
    if len(streams) != 1:
        raise ValueError(f"expected exactly one {kind} stream; found {len(streams)}")
    if kind == "video" and streams[0].get("disposition", {}).get("attached_pic"):
        raise ValueError("attached cover art is not a source video")
    return streams[0]


def _timing_tolerance(fps):
    # One output frame or one AAC packet, whichever is longer. This accommodates
    # codec/container rounding, never an arbitrary fraction of the whole movie.
    return max(1 / fps, 1024 / 48000) + 1e-6


def assemble(edl_path: str, audio_path: Optional[str] = None,
             output_path: Optional[str] = None, fps: float = DEFAULT_FPS,
             do_validate: bool = True, audio_mode: Optional[str] = None,
             width: Optional[int] = None, height: Optional[int] = None) -> str:
    """Three-stage assembly with explicit external/source/silent audio intent.

    A supplied external audio file retains the legacy external + 1080x1920
    behavior. Otherwise audio_mode is mandatory. Source/silent inherit matching
    source dimensions unless both dimensions are supplied. No audio is mixed.
    """
    edl_path = str(Path(edl_path).resolve())
    with open(edl_path, encoding="utf-8") as f:
        edl = json.load(f)
    scenes = _get_scenes(edl)
    meta = edl.get("metadata", {}) or {}
    if not scenes:
        raise ValueError("EDL has no scenes")
    if not math.isfinite(fps) or fps <= 0 or fps > 240:
        raise ValueError("fps must be finite and in (0, 240]")
    audio_path = audio_path or edl.get("audio_file")
    audio_mode = audio_mode or edl.get("audio_mode") or ("external" if audio_path else None)
    if audio_mode not in ("external", "source", "silent"):
        raise ValueError("declare --audio-mode source|silent, or supply external audio")
    if audio_mode != "external" and audio_path:
        raise ValueError("source/silent audio mode conflicts with external audio_file/--audio")
    if audio_mode == "external" and not audio_path:
        raise ValueError("external mode requires --audio or EDL.audio_file")
    if audio_path:
        audio_path = _resolve(audio_path, edl_path)
    output_path = str(Path(output_path or edl.get("output_file") or
                           Path(edl_path).parent / "成片.mp4").resolve())
    # Never silently replace a source or a prior deliverable.
    if Path(output_path).exists():
        raise ValueError("output already exists; choose a new output path")
    if Path(output_path).suffix.lower() != ".mp4":
        raise ValueError("output must be an MP4 path")
    sources = {str(Path(_resolve(_scene_source(s), edl_path)).resolve()) for s in scenes}
    if output_path in sources or output_path in (edl_path, audio_path):
        raise ValueError("output cannot overwrite input")
    probes = {source: _probe(source) for source in sources}
    videos = {source: _one_stream(probe, "video") for source, probe in probes.items()}
    sizes = {(int(v["width"]), int(v["height"])) for v in videos.values()}
    if (width is None) != (height is None):
        raise ValueError("width and height must be supplied together")
    if width is None:
        if audio_mode == "external":
            width, height = TARGET_WIDTH, TARGET_HEIGHT
        elif len(sizes) == 1:
            width, height = next(iter(sizes))
        else:
            raise ValueError("mixed source dimensions require explicit width and height")
    if any(type(n) is not int or n <= 0 or n > 8192 or n % 2 for n in (width, height)):
        raise ValueError("width/height must be positive even integers <=8192")
    tolerance = _timing_tolerance(fps)
    frames, timeline_end = [], 0.0
    source_channels = set()
    for scene in scenes:
        source = str(Path(_resolve(_scene_source(scene), edl_path)).resolve())
        start, end = float(scene["source_in"]), float(scene["source_out"])
        if not all(math.isfinite(n) for n in (start, end)) or start < 0 or end <= start:
            raise ValueError("invalid source interval")
        video = videos[source]
        if abs(float(video.get("start_time", 0))) > .001:
            raise ValueError("nonzero video stream origin requires explicit timestamp normalization")
        if end > _duration(video) + .001:
            raise ValueError("source interval exceeds video stream duration")
        for field, expected in (("timeline_start", timeline_end),
                                ("timeline_end", timeline_end + end - start)):
            if field not in scene or not math.isfinite(float(scene[field])) or abs(float(scene[field])-expected) > 1e-6:
                raise ValueError("timeline must be continuous and match source interval durations")
        timeline_end += end - start
        count = round((end - start) * fps)
        if count < 1:
            raise ValueError("scene shorter than one output frame")
        frames.append(count)
        if audio_mode == "source":
            audio = _one_stream(probes[source], "audio")
            channels = int(audio.get("channels", 0))
            if channels not in (1, 2):
                raise ValueError("source mode supports mono/stereo; no implicit surround downmix")
            source_channels.add(channels)
            audio_start = float(audio.get("start_time", 0))
            if not math.isfinite(audio_start) or abs(audio_start) > .001:
                raise ValueError("nonzero audio stream origin requires explicit timestamp normalization")
            if end > _duration(audio) + 1/48000:
                raise ValueError("source audio does not cover requested interval; no silence is invented")
    if len(source_channels) > 1:
        raise ValueError("mixed source channel counts require explicit upstream normalization")
    channels = next(iter(source_channels), 2)
    expected_duration = sum(frames) / fps
    if abs(expected_duration - timeline_end) > tolerance:
        raise ValueError("accumulated frame rounding changes duration; align scene durations to output frames")
    if "total_duration" in meta:
        declared_total = float(meta["total_duration"])
        if not math.isfinite(declared_total) or abs(declared_total - timeline_end) > .001:
            raise ValueError("metadata total_duration must match actual edit intervals")
    if do_validate:
        # Preserve all existing ordering/overlap checks, including same-source reverse rejection.
        canonical = dict(edl, scenes=[dict(s, source=_scene_source(s)) for s in scenes])
        _gate_validate(canonical, edl_path, meta.get("total_duration"), fps)
    if audio_mode == "external":
        external = _one_stream(_probe(audio_path), "audio")
        if abs(float(external.get("start_time", 0))) > .001:
            raise ValueError("external audio must start at zero")
        audio_duration = _duration(external)
        if abs(audio_duration - expected_duration) > tolerance:
            raise ValueError(f"external audio duration {audio_duration:.6f}s differs from edit "
                             f"{expected_duration:.6f}s; tolerance={tolerance:.6f}s (frame/AAC rounding only)")
    print(f"assemble {len(scenes)} scenes, {width}x{height}, {fps}fps, audio={audio_mode}")
    print(f"duration={expected_duration:.6f}s; validation tolerance={tolerance:.6f}s")
    if audio_mode == "source":
        print(f"source audio: trim with each scene, 48kHz PCM/{channels} channels, encode AAC once")
    if audio_mode == "external" and any(_streams(p, "audio") for p in probes.values()):
        print("external audio requested: source audio is replaced, never mixed")
    if abs(expected_duration-timeline_end) > 1e-6:
        print(f"frame quantization: requested {timeline_end:.6f}s -> {expected_duration:.6f}s")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="video_assemble_", dir=Path(output_path).parent) as tmpdir:
        segments = _extract_segments(scenes, edl_path, tmpdir, fps, frames, width, height, audio_mode, channels)
        assembled = _concat_segments(segments, tmpdir)
        candidate = str(Path(tmpdir) / "candidate.mp4")
        _finish_audio(assembled, audio_path, candidate, audio_mode)
        _verify_output(candidate, sum(frames), fps, width, height, audio_mode)
        # Atomic no-clobber publication on the same filesystem, after validation.
        os.link(candidate, output_path)
    print("complete: " + output_path)
    return output_path


def _extract_segments(scenes, edl_path, tmpdir, fps, frames, width, height, audio_mode, channels):
    """Video plus PCM intermediates avoid AAC priming gaps at each splice."""
    scale = (f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
             f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:{PAD_COLOR},setsar=1,setpts=PTS-STARTPTS")
    segments = []
    for i, (scene, count) in enumerate(zip(scenes, frames)):
        duration = count / fps
        # MOV retains a frame-representable video clock plus PCM. Matroska's
        # millisecond clock rounds 24fps cuts and makes stream-copy concat
        # publish a non-CFR average even when all segment frame counts match.
        target = str(Path(tmpdir) / f"seg_{i:05d}.mov")
        command = ["ffmpeg", "-v", "error", "-nostdin", "-y", "-i",
                   _resolve(_scene_source(scene), edl_path), "-ss", str(scene["source_in"]),
                   "-t", f"{duration:.12f}", "-map", "0:v:0", "-vf", scale,
                   "-r", str(fps), "-fps_mode", "cfr", "-c:v", "libx264",
                   "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p"]
        if audio_mode == "source":
            command += ["-map", "0:a:0", "-af", "asetpts=PTS-STARTPTS",
                        "-c:a", "pcm_s16le", "-ar", "48000", "-ac", str(channels)]
        else:
            command += ["-an"]
        _run(command + [target])
        # A truncated source must not become a 'successful' shorter concat.
        _verify_output(target, count, fps, width, height, audio_mode, decode=False)
        segments.append(target)
    return segments


def _concat_segments(segments, tmpdir):
    concat_txt = Path(tmpdir) / "concat.txt"
    # Intermediates have fixed safe basenames; avoid platform-dependent escaping.
    concat_txt.write_text("".join(f"file '{Path(p).name}'\n" for p in segments), encoding="utf-8")
    assembled = str(Path(tmpdir) / "assembled.mov")
    _run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-f", "concat", "-safe", "1",
          "-i", str(concat_txt), "-map", "0", "-c", "copy", assembled])
    return assembled


def _finish_audio(video_file, audio_file, output_path, audio_mode):
    command = ["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", video_file]
    if audio_mode == "external":
        command += ["-i", audio_file, "-map", "0:v:0", "-map", "1:a:0"]
    else:
        command += ["-map", "0:v:0"]
        if audio_mode == "source":
            command += ["-map", "0:a:0"]
    command += ["-c:v", "copy"]
    if audio_mode == "silent":
        command += ["-an"]
    else:
        command += ["-c:a", "aac", "-b:a", "256k", "-ar", "48000"]
    # No -shortest, padding, mixing or duration crop: preserve both complete streams.
    _run(command + ["-movflags", "+faststart", output_path])


def _verify_output(path, frame_count, fps, width, height, audio_mode, decode=True):
    probe = _probe(path, count_frames=True)
    video = _one_stream(probe, "video")
    expected = frame_count / fps
    tolerance = _timing_tolerance(fps)
    if (int(video["width"]), int(video["height"])) != (width, height):
        raise ValueError("output dimensions differ from requested canvas")
    if abs(float(Fraction(video["avg_frame_rate"]))-fps) > 1e-6:
        raise ValueError("output FPS differs from requested FPS")
    if int(video.get("nb_read_frames", -1)) != frame_count:
        raise ValueError("output video frame count differs from edit")
    if abs(_duration(video)-expected) > tolerance:
        raise ValueError("output video duration differs from edit")
    audio = _streams(probe, "audio")
    # External intermediates are deliberately silent until the one external track is attached.
    needs_audio = audio_mode == "source" or (audio_mode == "external" and decode)
    if len(audio) != (1 if needs_audio else 0):
        raise ValueError("output audio streams do not match declared intent")
    if audio and abs(_duration(audio[0])-expected) > tolerance:
        raise ValueError("output audio duration differs from edit")
    if abs(float(probe["format"]["duration"])-expected) > tolerance:
        raise ValueError("output container duration differs from edit")
    if decode:
        _run(["ffmpeg", "-v", "error", "-xerror", "-nostdin", "-i", str(path),
              "-map", "0:v:0", "-map", "0:a?", "-f", "null", "-"])


def main(argv=None):
    parser = argparse.ArgumentParser(description="EDL assembly with explicit audio intent and canvas")
    parser.add_argument("edl")
    parser.add_argument("--audio", help="external audio; explicitly replaces source audio")
    parser.add_argument("--audio-mode", choices=("external", "source", "silent"))
    parser.add_argument("--out")
    parser.add_argument("--fps", type=float, default=DEFAULT_FPS)
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--no-validate", action="store_true", help="legacy EDL checks only; media checks remain mandatory")
    args = parser.parse_args(argv)
    try:
        assemble(args.edl, args.audio, args.out, args.fps, not args.no_validate,
                 args.audio_mode, args.width, args.height)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
