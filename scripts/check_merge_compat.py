#!/usr/bin/env python3
"""
🎬 sansheng-video 拼接前兼容性校验器
==================================================
多片段拼接 (concat / 转场) 前先验一遍: 零/负时长直接硬失败, 混音/无音、分辨率、FPS 不一致告警,
转场时长 ≥ 最短片段硬失败、> 50% 告警. 纯校验、零副作用, 不动任何文件.

定位 (sansheng-video 装配模式拼接前):
- 多 shot 拼接最常见的"静默坏片": 某段时长为 0 / 一段有音一段没音 / 分辨率混搭 / 转场比片段还长
- ffmpeg concat 经常不报错却出坏成片 → 拼之前先 probe + 校验, 把问题挡在拼接前

默认值 (常用 9:16 竖屏):
    分辨率 1080x1920, fps 30 — ffprobe 读不到某项时用这套默认补齐再比对

==================================================
📦 上游来源 (vendor)
- repo : KyaniteLabs/mcp-video
  URL  : https://github.com/KyaniteLabs/mcp-video
  文件 : mcp_video/merge_guardrails.py 里的 validate_merge_compatibility()
- License        : Apache-2.0 (已核实非 Anthropic Proprietary, vendor 合法, 保留来源署名)
- 锁定 upstream commit : ba9d64048f095688ee3d3b18aa1d3f1fa7a0cd7e (2026-05-30 核对的 HEAD)
- 同步日期       : 2026-05-30
- vendored into sansheng-video, 改动点:
    1) 忠实保留上游 5 道校验逻辑 (零/负时长硬失败、混音/无音告警、分辨率/FPS 不一致告警、转场 ≥最短硬失败、>50% 告警);
    2) 拆掉对上游 VideoInfo 模型的依赖, 改成本地 dataclass + 内置 ffprobe 子进程探测 (上游是"已探好的 VideoInfo 进来", 这里自己 probe);
    3) 默认分辨率/fps 改 9:16 1080x1920 / 30; ffprobe 缺某项时用默认补齐;
    4) 异常类换成本地 MergeCompatError, 中文报错, CLI 退出码携带语义.
    修改时保留来源署名与行为回归

使用方法:
    python check_merge_compat.py clip1.mp4 clip2.mp4 clip3.mp4
    python check_merge_compat.py clip1.mp4 clip2.mp4 --transition 0.5
    python check_merge_compat.py --from-edl 视频稿/edl.json     # 读 EDL 抽 distinct source 校验
    # 退出码: 0 = 通过(可能含告警); 1 = 硬失败(零时长/转场过长); 2 = 用法/探测错误
    # --from-edl: source 相对 edl.json 目录解析, 含空格路径不被错切 (替代脆弱的 jq|xargs 管线)

前置条件:
    ffprobe 在 PATH 里 (跟 ffmpeg 一起装; 使用 setup.py --check 检查)
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


# ---- 常用 9:16 竖屏默认值: ffprobe 读不到某项时补齐再比对 ----
DEFAULT_WIDTH = 1080      # 9:16 竖屏标准短边（ffprobe 缺 width 时按竖版基准宽兜底）
DEFAULT_HEIGHT = 1920     # 9:16 竖屏标准长边（ffprobe 缺 height 时按竖版基准高兜底）
DEFAULT_FPS = 30.0        # 默认兜底帧率（对齐 hyperframes npm run render --fps 30；ffprobe 读不到 r_frame_rate 时用）


class MergeCompatError(Exception):
    """硬失败: 零/负时长片段、转场时长过长等, 必须中止拼接."""


@dataclass
class VideoInfo:
    path: str
    duration: float
    width: int
    height: int
    fps: float
    audio_codec: Optional[str]


def _parse_fps(rate: str) -> float:
    """ffprobe 的 r_frame_rate 形如 '30/1' 或 '30000/1001', 解析成 float."""
    try:
        if "/" in rate:
            num, den = rate.split("/", 1)
            den_f = float(den)
            return float(num) / den_f if den_f else DEFAULT_FPS
        return float(rate)
    except Exception:
        return DEFAULT_FPS


def _resolve_source(path: str, edl_path: str) -> str:
    """
    把 scene.source 解析成磁盘上的实际路径。

    契约与 assemble_edl._resolve / validate_edl._resolve_source 完全一致（三门统一）：
    相对路径按 **edl.json 所在目录**（而非 cwd）解析；绝对路径原样返回。
    """
    p = Path(path)
    if p.is_absolute():
        return str(p)
    return str((Path(edl_path).resolve().parent / p))


def distinct_sources_from_edl(edl_path: str) -> List[str]:
    """
    读 edl.json，按 EDL 出现顺序抽出 distinct 的 scene.source（已解析为实体路径）。

    替代脆弱的 `jq … | xargs` shell 管线：直接在 Python 里取 source、相对 edl.json 目录
    解析、去重，根治含空格路径被 xargs 错切的问题（含空格的整条路径作为单个元素，
    不会被拆成两个不存在的片段）。

    distinct：同一段素材被多个 scene 引用（不同 source_in）时只探一次，避免重复 probe。
    顺序：按首次出现顺序保留，报告里片段次序与 EDL 一致，便于人工核对。

    schema 与 assemble_edl / validate_edl 对齐：顶层 "scenes"（兼容上游别名 "cuts"），
    每段 "source"（兼容上游别名 "source_file"）。
    """
    with open(edl_path, "r", encoding="utf-8") as f:
        edl = json.load(f)

    scenes = edl.get("scenes") or edl.get("cuts") or []
    seen = set()
    ordered: List[str] = []
    for scene in scenes:
        raw = scene.get("source") or scene.get("source_file")
        if not raw:
            continue
        resolved = _resolve_source(raw, edl_path)
        if resolved not in seen:
            seen.add(resolved)
            ordered.append(resolved)
    return ordered


def probe_video_info(path: str) -> VideoInfo:
    """用 ffprobe 探一个片段的时长/分辨率/fps/音频编码; 读不到的项用 9:16 默认补齐."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise MergeCompatError(
            "未找到 ffprobe. 先跑 setup.py --check 自检, 按提示装 ffmpeg（Mac: brew install ffmpeg；Windows: winget/choco） (自带 ffprobe)"
        )

    cmd = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type,codec_name,width,height,r_frame_rate:format=duration",
        "-of",
        "json",
        path,
    ]
    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or "").strip().splitlines()[-6:])
        raise MergeCompatError(f"ffprobe 探测失败: {path}\n{tail}")

    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        raise MergeCompatError(f"ffprobe 输出无法解析: {path}")

    streams = data.get("streams") or []
    fmt = data.get("format") or {}

    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    width = int(video_stream.get("width") or DEFAULT_WIDTH) if video_stream else DEFAULT_WIDTH
    height = int(video_stream.get("height") or DEFAULT_HEIGHT) if video_stream else DEFAULT_HEIGHT
    fps = _parse_fps(video_stream.get("r_frame_rate", "")) if video_stream else DEFAULT_FPS

    try:
        duration = float(fmt.get("duration") or 0.0)
    except (TypeError, ValueError):
        duration = 0.0

    audio_codec = audio_stream.get("codec_name") if audio_stream else None

    return VideoInfo(
        path=path,
        duration=duration,
        width=width,
        height=height,
        fps=fps,
        audio_codec=audio_codec,
    )


def validate_merge_compatibility(
    infos: List[VideoInfo],
    transition_duration: float = 0.0,
) -> List[str]:
    """校验多片段能否安全拼接. 返回告警列表; 硬失败抛 MergeCompatError.

    忠实保留上游 5 道校验:
      1) 零/负时长 → 硬失败
      2) 混音/无音 → 告警
      3) 分辨率不一致 → 告警
      4) FPS 不一致 → 告警
      5) 转场时长 ≥ 最短片段 → 硬失败; > 最短 50% → 告警
    """
    warnings: List[str] = []
    if len(infos) < 2:
        return warnings

    # 1. 转场数学之前, 先抓零/负时长片段
    for info in infos:
        if info.duration <= 0:
            raise MergeCompatError(
                f"片段 '{info.path}' 时长为零或负 ({info.duration})."
            )

    # 2. 混音 / 无音 混搭
    has_audio = [i.audio_codec is not None for i in infos]
    if any(has_audio) and not all(has_audio):
        warnings.append(
            "拼接片段里有的带音轨、有的没有. 无音片段可能触发 concat demuxer 报错或静默出空音轨; "
            "建议把所有片段统一成同样的『有/无音轨』状态."
        )

    # 3. 分辨率不一致
    resolutions = {(i.width, i.height) for i in infos}
    if len(resolutions) > 1:
        warnings.append(
            f"片段分辨率不一致: {sorted(resolutions)}. 拼接会通过重编码强行归一化 (变慢, 可能糊)."
        )

    # 4. FPS 不一致
    fps_values = sorted({round(i.fps, 2) for i in infos})
    if len(fps_values) > 1:
        warnings.append(f"片段帧率不一致: {fps_values}. 成片可能卡顿或丢帧.")

    # 5. 时长 vs 转场
    if transition_duration > 0:
        min_dur = min(i.duration for i in infos)
        if transition_duration >= min_dur:
            raise MergeCompatError(
                f"转场时长 ({transition_duration}s) 必须小于最短片段时长 ({min_dur:.2f}s)."
            )
        if transition_duration > min_dur * 0.5:
            warnings.append(
                f"转场时长 ({transition_duration}s) 超过最短片段 ({min_dur:.2f}s) 的 50%, 转场可能盖过画面内容."
            )

    return warnings


def main(argv: Optional[List[str]] = None) -> int:
    # Windows GBK 控制台打印 emoji 会 UnicodeEncodeError → 强制 stdout/stderr 走 UTF-8（等价 PYTHONUTF8=1）
    for _s in (sys.stdout, sys.stderr):
        _rc = getattr(_s, "reconfigure", None)
        if _rc:
            try:
                _rc(encoding="utf-8")
            except Exception:
                pass
    parser = argparse.ArgumentParser(
        description="多片段拼接前的兼容性校验 (零时长/混音/分辨率/FPS/转场时长). 纯校验, 不动文件."
    )
    parser.add_argument("clips", nargs="*", help="待拼接的片段 (>=2 个才会真正校验); 与 --from-edl 二选一")
    parser.add_argument(
        "--from-edl", "--edl",
        dest="from_edl",
        default=None,
        help="直接读 edl.json 抽 distinct source 来校验 (相对 edl.json 目录解析, 含空格路径不被错切); "
             "替代脆弱的 jq | xargs shell 管线",
    )
    parser.add_argument(
        "--transition",
        type=float,
        default=0.0,
        help="片段间转场时长 (秒), 默认 0 (硬切, 不做转场校验)",
    )
    args = parser.parse_args(argv)

    # 片段来源: --from-edl (读 edl.json 抽 source) 与裸 clips 列表二选一
    if args.from_edl:
        if args.clips:
            sys.stderr.write("❌ 用法: --from-edl 与裸 clips 列表互斥, 二选一.\n")
            return 2
        try:
            clips = distinct_sources_from_edl(args.from_edl)
        except (OSError, json.JSONDecodeError) as e:
            sys.stderr.write(f"❌ 读取 EDL 失败: {args.from_edl}\n{e}\n")
            return 2
        if not clips:
            sys.stderr.write(f"❌ EDL 里没抽到任何 source: {args.from_edl}\n")
            return 2
    else:
        clips = args.clips
        if not clips:
            sys.stderr.write("❌ 用法: 给至少 1 个片段, 或用 --from-edl <edl.json>.\n")
            return 2

    if len(clips) < 2:
        sys.stdout.write("ℹ️  只有 1 个 distinct 片段, 无需拼接校验. 通过.\n")
        return 0

    try:
        infos = [probe_video_info(c) for c in clips]
        warnings = validate_merge_compatibility(infos, transition_duration=args.transition)
    except MergeCompatError as e:
        sys.stderr.write(f"❌ 硬失败 (不可拼接): {e}\n")
        return 1
    except Exception as e:  # noqa: BLE001 — 探测/用法层意外
        sys.stderr.write(f"❌ 校验出错: {type(e).__name__}: {e}\n")
        return 2

    # 探测信息一览
    sys.stdout.write("📋 片段信息:\n")
    for i in infos:
        audio = i.audio_codec or "无音轨"
        sys.stdout.write(
            f"   - {i.path}: {i.width}x{i.height} @ {round(i.fps, 2)}fps, "
            f"{i.duration:.2f}s, 音频={audio}\n"
        )

    if warnings:
        sys.stdout.write(f"\n⚠️  {len(warnings)} 条告警 (可拼接, 但留意):\n")
        for w in warnings:
            sys.stdout.write(f"   - {w}\n")
    else:
        sys.stdout.write("\n✅ 全部兼容, 可安全拼接.\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
