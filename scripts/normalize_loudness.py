#!/usr/bin/env python3
"""
🎬 sansheng-video 响度归一化器 (loudnorm / EBU R128)
==================================================
把成片音轨归一化到目标平台的标准响度 (LUFS), 防止"上传后被平台二压降音 / 时大时小"问题.
只动音轨 (-c:v copy), 画面零重编码, 秒级完成.

定位 (sansheng-video 出片末端):
- 抖音 / 视频号 / 小红书 各家有自己的目标响度; 不归一化 → 平台自动增益乱跳, 观感忽大忽小
- 在 render 出片之后跑一道, 按平台喂不同 LUFS, 一键出 "成片-norm.mp4"

平台 LUFS 映射 (集成响度 I):
    douyin    抖音    -14 LUFS
    shipinhao 视频号  -16 LUFS
    xhs       小红书  -14 LUFS
真峰值 TP 固定 -1.5 dBTP (留 headroom 防平台二压削顶); LRA (响度范围) 可调, 默认 11.0 LU.

==================================================
📦 上游来源 (vendor)
- repo : KyaniteLabs/mcp-video
  URL  : https://github.com/KyaniteLabs/mcp-video
  文件 : mcp_video/engine_audio_normalize.py 里的 normalize_audio()
- License        : Apache-2.0 (已核实非 Anthropic Proprietary, vendor 合法, 保留来源署名)
- 锁定 upstream commit : ba9d64048f095688ee3d3b18aa1d3f1fa7a0cd7e (2026-05-30 核对的 HEAD)
- 同步日期       : 2026-05-30
- vendored into sansheng-video, 改动点:
    1) 拆掉上游对 mcp_video 内部 helper 的整套依赖, 改成自包含的 ffmpeg 子进程 (subprocess), 不拉任何 mcp-video 模块;
    2) 新增平台→LUFS 映射 (抖音/视频号/小红书), CLI 用 --platform 选, 也可 --lufs 手动覆盖;
    3) 忠实保留上游核心: target_lufs 边界校验 (-70~-5 防呆)、TP 固定 -1.5 dBTP、loudnorm 滤镜、-c:v copy 只动音轨;
    4) LRA 参数化 (--lra), 校验 ffmpeg 是否带 loudnorm 滤镜.
    ⚠️ 只摘 normalize 逻辑, 严格未碰上游自带的 music_generation/minimax.py (本模块不调用生成服务).
    修改时保留来源署名与行为回归

使用方法:
    python normalize_loudness.py 成片.mp4 --platform douyin --out 成片-norm.mp4
    python normalize_loudness.py 成片.mp4 --platform shipinhao
    python normalize_loudness.py 成片.mp4 --lufs -13 --lra 9      # 手动覆盖目标响度

前置条件:
    ffmpeg 在 PATH 里, 且编译时带 loudnorm 滤镜 (Gyan/官方 build 默认都带)
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional


# ---- 平台 → 集成响度 (LUFS) 映射 ----
PLATFORM_LUFS = {
    "douyin": -14.0,     # 抖音
    "shipinhao": -16.0,  # 视频号
    "xhs": -14.0,        # 小红书
}

# 真峰值固定 -1.5 dBTP (留 headroom, 上游核心约定: TP 与目标 LUFS 无关, 始终固定)
TRUE_PEAK_DBTP = -1.5


def _err(msg: str) -> None:
    sys.stderr.write(f"❌ {msg}\n")


def _ffmpeg_has_loudnorm() -> bool:
    """确认 ffmpeg 编译时带 loudnorm 滤镜 (对应上游 _require_filter)."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    try:
        proc = subprocess.run(
            [ffmpeg, "-hide_banner", "-filters"],
            check=False,
            capture_output=True,
            text=True,
        )
        return "loudnorm" in (proc.stdout or "")
    except Exception:
        return False


def _validate_target_lufs(target_lufs: float) -> None:
    """上游核心防呆: target_lufs 必须落在 -70 ~ -5 之间."""
    if not isinstance(target_lufs, (int, float)) or not (-70 <= target_lufs <= -5):
        raise ValueError(
            f"target_lufs 必须在 -70 ~ -5 之间, 收到 {target_lufs} (LUFS 是负值; 太大或太小都不合理)"
        )


def _default_out(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}-norm{input_path.suffix or '.mp4'}")


def normalize_loudness(
    input_path: str,
    target_lufs: float,
    lra: float = 11.0,
    output_path: Optional[str] = None,
) -> Path:
    """把 input_path 的音轨归一化到 target_lufs, 画面 copy 不重编码, 返回输出路径.

    Args:
        input_path : 输入成片
        target_lufs: 目标集成响度 (LUFS), 须落在 -70 ~ -5
        lra        : 目标响度范围 (LU), 默认 11.0
        output_path: 输出路径; None 则自动派生 "<名>-norm.<后缀>"
    """
    src = Path(input_path)
    if not src.exists():
        raise FileNotFoundError(f"输入文件不存在: {src}")

    _validate_target_lufs(target_lufs)

    if not _ffmpeg_has_loudnorm():
        raise RuntimeError(
            "未找到带 loudnorm 滤镜的 ffmpeg. 先跑 setup.py --check 自检, "
            "按提示装 ffmpeg（Mac: brew install ffmpeg；Windows: winget/choco，Gyan/官方 build 默认带 loudnorm）"
        )

    out = Path(output_path) if output_path else _default_out(src)
    out.parent.mkdir(parents=True, exist_ok=True)

    # loudnorm: I=集成响度, TP=真峰值(固定 -1.5), LRA=响度范围
    audio_filter = f"loudnorm=I={target_lufs}:TP={TRUE_PEAK_DBTP}:LRA={lra}"

    cmd: List[str] = [
        "ffmpeg",
        "-hide_banner",
        "-y",
        "-i",
        str(src),
        "-c:v",
        "copy",          # 只动音轨, 画面零重编码
        "-af",
        audio_filter,
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(out),
    ]

    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or "").strip().splitlines()[-12:])
        raise RuntimeError(f"ffmpeg 归一化失败 (exit {proc.returncode}):\n{tail}")

    return out


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
        description="把成片音轨按目标平台响度归一化 (loudnorm / EBU R128), 只动音轨不重编码画面."
    )
    parser.add_argument("input", help="输入成片 (如 成片.mp4)")
    parser.add_argument(
        "--platform",
        choices=sorted(PLATFORM_LUFS.keys()),
        help="目标平台 (douyin 抖音 -14 / shipinhao 视频号 -16 / xhs 小红书 -14)",
    )
    parser.add_argument(
        "--lufs",
        type=float,
        default=None,
        help="手动指定目标集成响度 (LUFS, -70~-5); 给了它就覆盖 --platform",
    )
    parser.add_argument("--lra", type=float, default=11.0, help="目标响度范围 (LU), 默认 11.0")
    parser.add_argument("--out", default=None, help="输出路径; 缺省自动派生 <名>-norm.<后缀>")
    args = parser.parse_args(argv)

    # 目标响度: --lufs 优先, 否则按 --platform 查表; 两者都没给则报错
    if args.lufs is not None:
        target = args.lufs
    elif args.platform:
        target = PLATFORM_LUFS[args.platform]
    else:
        _err("必须给 --platform (douyin/shipinhao/xhs) 或 --lufs 之一")
        return 2

    try:
        out = normalize_loudness(args.input, target_lufs=target, lra=args.lra, output_path=args.out)
    except (ValueError, FileNotFoundError, RuntimeError) as e:
        _err(str(e))
        return 1

    label = args.platform or f"{target} LUFS"
    sys.stdout.write(f"✅ 已归一化到 {label} (I={target} / TP={TRUE_PEAK_DBTP}dBTP / LRA={args.lra}) → {out}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
