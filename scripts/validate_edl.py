#!/usr/bin/env python3
"""
sansheng-video EDL 校验器 -- 出片前对 scene 序列 EDL 做 9 项机检.

定位（v2/v3 出片管线）：
- EDL = 一条 scene 序列（hyperframes 章节 html / 录屏切片 / Veo broll mp4 的剪辑决策表）。
- 本脚本是 `npm run dev` preview 人眼硬验收的**前置机检**：先用机器把
  时间线空洞 / 倒序 / 重叠 / 关键帧闪帧这类"肉眼难逐帧抓"的硬伤拦掉，再上人眼。
- 第 7 项把上游"beat 对齐"语义转译为"word_ts/卡点对齐容差"，落地 「词到·图到·拍到」三同步里的"词到"轴；不照搬上游"音乐先行"的节拍逻辑。

校验项（本工具的 9 项）：
  ① 时间线连续    scene 首尾相接、无空洞（上游 check_contiguity）
  ② 顺序非递减    同 source 内 source_in 不回退（上游 check_source_ordering）
  ③ source 区间   source_out > source_in（上游 check_source_validity）
  ④ 覆盖整片      末尾 scene 盖满总时长（上游 check_coverage）
  ⑤ 精确去重      (source, source_in) 不重复（上游 check_no_repeats）
  ⑥ 区间重叠      同 source O(n log n) 扫描查 [source_in,source_out) 重叠（上游 check_source_overlaps）
  ⑦ 卡点对齐      word_ts 命中视觉事件容差（上游 check_beat_alignment 转译，对齐 词到）
  ⑧ head-buffer   source_in 距素材头 ≥3 帧（本项目新增，防 ffmpeg -ss 回退关键帧闪帧）
  ⑨ source 存在   scene.source 实体文件在盘上（本项目新增，相对 edl.json 目录解析，对齐 assemble_edl）

「跳过」≠「通过」：缺数据的项（如无 total_duration / 无 edl_path）单列 skipped，不混进全绿。
装配模式（--assemble / require_coverage=True）下，total_duration 与 source 实体文件视为必需，缺则判 fail。

CLI：
    python validate_edl.py <edl.json>
    python validate_edl.py <edl.json> --fps 30 --total 62.5
    python validate_edl.py <edl.json> --assemble   # 装配模式：total_duration/source 必需

退出码：0 全过；1 有问题（CI / 出片管线可据此卡门）。
"""

# ==============================================================================
# 上游来源与修改说明
# ------------------------------------------------------------------------------
# 来源 repo : guigulaoshi/music-video-director-skill
# URL       : https://github.com/guigulaoshi/music-video-director-skill
# 取自文件   : mvd/validate.py（7 个纯函数校验 + validate_edl 聚合 + assert_valid_edl）
# License   : MIT（已核实非 Anthropic Proprietary，vendor 合法，保留来源署名即可）
# 锁定 commit: 06abf674e936eefd69f053759f673e3c72f71e2e（gh api ...commits/HEAD .sha）
# 同步日期   : 2026-05-30
#
# vendored into sansheng-video，改动点：
#   1. cuts/beats（音乐先行）语义转译为 scene/word_ts（口播先行）：
#      source_file→source、lyric→voiceover、beats→word_ts、section 保留、新增 timeline_*。
#   2. 上游 check_beat_alignment 改写为 check_wordts_alignment：对齐 「词到」轴，
#      校验视觉事件落点 word_ts 命中容差，而非吸附 BGM 拍点（拍到轴交给 _analyze.py，不在此脚本）。
#   3. 新增第 8 项 check_head_buffer：source_in 距素材头 ≥3 帧 head-buffer，防 ffmpeg -ss
#      回退最近关键帧的闪帧（对齐 assemble_edl 装配阶段，上游无此项）。
#   4. 去掉上游 numpy 硬依赖（纯 Python 实现最近距离扫描），CLI 报告中文化。
# 修改时保留来源署名与行为回归。
# ==============================================================================

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

# 默认帧率：sansheng-video 9:16 成片基准（与 render high 档一致）
DEFAULT_FPS = 30.0
# head-buffer 帧数：source_in 距素材头至少留这么多帧，防关键帧回退闪帧
HEAD_BUFFER_FRAMES = 3


def _resolve_source(path: str, edl_path: Optional[str]) -> str:
    """
    把 scene.source 解析成磁盘上的实际路径。

    契约与 assemble_edl._resolve / check_merge_compat 完全一致（三门统一）：
    相对路径按 **edl.json 所在目录**（而非 cwd）解析；绝对路径原样返回。
    edl_path 为 None（纯结构校验、无文件落地的单测）时退回原样字符串。
    """
    p = Path(path)
    if p.is_absolute() or edl_path is None:
        return str(p)
    return str((Path(edl_path).resolve().parent / p))


# ---------------------------------------------------------------------------
# ① 时间线连续（scene 首尾相接，无空洞 / 无重叠）
# ---------------------------------------------------------------------------
def check_contiguity(scenes: list, tolerance_s: float = 0.002) -> list:
    """每个 scene 的 timeline_start 必须等于上一个 scene 的 timeline_end。"""
    errors = []
    for i in range(1, len(scenes)):
        prev_end = scenes[i - 1]["timeline_end"]
        curr_start = scenes[i]["timeline_start"]
        gap = abs(curr_start - prev_end)
        if gap > tolerance_s:
            errors.append(
                f"scene #{scenes[i-1].get('n', i)}（end={prev_end:.3f}）与 "
                f"scene #{scenes[i].get('n', i+1)}（start={curr_start:.3f}）之间断裂：{gap*1000:.1f}ms"
            )
    return errors


# ---------------------------------------------------------------------------
# ② 顺序非递减（同一 source 内 source_in 不回退）
# ---------------------------------------------------------------------------
def check_source_ordering(scenes: list, tolerance_s: float = 0.001) -> list:
    """同一 source 内，source_in 必须非递减（回放素材时不倒带）。"""
    high_water = defaultdict(float)
    errors = []
    for i, scene in enumerate(scenes):
        src = scene["source"]
        si = scene["source_in"]
        hw = high_water[src]
        if hw > 0 and si < hw - tolerance_s:
            errors.append(
                f"scene #{scene.get('n', i+1)}：{src!r} source_in={si:.3f} < "
                f"前序 source_out={hw:.3f}（素材倒带）"
            )
        high_water[src] = max(hw, scene["source_out"])
    return errors


# ---------------------------------------------------------------------------
# ③ source 区间合法（source_out > source_in，且 >= 下限）
# ---------------------------------------------------------------------------
def check_source_validity(scenes: list, min_source_in: float = 0.0) -> list:
    """source_out > source_in；source_in >= min_source_in。"""
    errors = []
    for i, scene in enumerate(scenes):
        si, so = scene["source_in"], scene["source_out"]
        n = scene.get("n", i + 1)
        if so <= si:
            errors.append(f"scene #{n}：source_out={so:.3f} <= source_in={si:.3f}")
        if si < min_source_in:
            errors.append(f"scene #{n}：source_in={si:.3f} < 下限 {min_source_in:.3f}")
    return errors


# ---------------------------------------------------------------------------
# ④ 覆盖整片总时长（末尾 scene 盖满）
# ---------------------------------------------------------------------------
def check_coverage(scenes: list, total_duration: float, tolerance_s: float = 0.5) -> list:
    """最后一个 scene 的 timeline_end 必须在 total_duration 容差内（无尾部空洞）。"""
    if not scenes:
        return ["EDL 没有任何 scene"]
    last_end = scenes[-1]["timeline_end"]
    gap = abs(last_end - total_duration)
    if gap > tolerance_s:
        return [
            f"末尾 scene 结束于 {last_end:.3f}s，但整片总时长是 {total_duration:.3f}s"
            f"（差 {gap:.3f}s，容差 {tolerance_s}s）"
        ]
    return []


# ---------------------------------------------------------------------------
# ⑤ 精确去重（(source, source_in) 不重复）
# ---------------------------------------------------------------------------
def check_no_repeats(scenes: list) -> list:
    """同一 (source, source_in) 组合不应出现两次（防同一帧素材重复用）。"""
    seen = {}
    errors = []
    for i, scene in enumerate(scenes):
        n = scene.get("n", i + 1)
        key = (scene["source"], round(scene["source_in"], 2))
        if key in seen:
            errors.append(
                f"scene #{n} 复用了 {scene['source']!r} 的 source_in={scene['source_in']:.2f}"
                f"（与 scene #{seen[key]} 重复）"
            )
        seen[key] = n
    return errors


# ---------------------------------------------------------------------------
# ⑥ 区间重叠（同 source O(n log n) 扫描查 [source_in,source_out) 重叠）
# ---------------------------------------------------------------------------
def check_source_overlaps(scenes: list, tolerance_s: float = 0.001) -> list:
    """
    同一 source 下，任意两个 scene 的 [source_in, source_out) 区间不得重叠
    （无论它们在 EDL 里的顺序）。重叠 = A.source_in < B.source_out 且 B.source_in < A.source_out。

    catches：同一段素材被两个不同 scene 引用 → 观众看到重复画面。
    按 source_in 排序后做区间扫描，b_in >= a_out 即可提前 break，整体 O(n log n)。
    """
    by_source = defaultdict(list)
    for i, scene in enumerate(scenes):
        src = scene["source"]
        si = float(scene["source_in"])
        so = float(scene["source_out"])
        idx = scene.get("n", i + 1)
        by_source[src].append((idx, si, so))

    errors = []
    for src, intervals in by_source.items():
        name = os.path.basename(src)
        intervals.sort(key=lambda x: x[1])  # 按 source_in 排序
        for j in range(len(intervals)):
            for k in range(j + 1, len(intervals)):
                idx_a, a_in, a_out = intervals[j]
                idx_b, b_in, b_out = intervals[k]
                # b_in 已 >= a_out（含容差），后续不可能再重叠 → break
                if b_in >= a_out - tolerance_s:
                    break
                overlap_start = max(a_in, b_in)
                overlap_end = min(a_out, b_out)
                overlap = overlap_end - overlap_start
                errors.append(
                    f"{name!r} 内重叠：scene #{idx_a} [{a_in:.3f}→{a_out:.3f}] "
                    f"与 scene #{idx_b} [{b_in:.3f}→{b_out:.3f}] 重叠 {overlap:.3f}s"
                )
    return errors


# ---------------------------------------------------------------------------
# ⑦ 卡点对齐（word_ts 命中视觉事件容差 -- 对齐 「词到」轴）
# ---------------------------------------------------------------------------
def check_wordts_alignment(
    scenes: list,
    word_ts: Optional[list] = None,
    fps: float = DEFAULT_FPS,
    tolerance_ms: float = 30.0,
    early_frames: int = 2,
) -> list:
    """
    上游 check_beat_alignment 的口播先行转译版。

    校验：每个非开场 scene 的视觉切换时刻（timeline_start），必须命中**某个口播词级
    时间戳** word_ts[i]（在 tolerance_ms 容差内，允许提前 early_frames 帧预入场）。
    落地 「词到」--视觉事件锚词级时间戳，而非固定等差 stagger。

    转译说明（与上游差异）：
    - 上游对齐 BGM beat grid（音乐先行）；本工具对齐 word_ts（口播先行）。
    - 上游 early_frames 默认 2（视觉略提前于拍点入场更跟手），此处沿用同口径。
    - section == 'intro' 且 timeline_start == 0.0 的开场 scene 豁免（可在首词前起片）。
    - 每个 scene 可携带 `word_ts` 字段（该 scene 内自己的词级时间戳）；若无，则回退
      到传入的全片 word_ts 列表。两者皆空 → 跳过本项（无词级数据时不阻塞）。

    注意：BGM 拍点可由项目已有分析器提供，
    本脚本只管「词到」，冲突时语义优先（不为凑拍硬挪 scene 起点）。
    """
    # 汇总可用的全片 word_ts（scene 自带的优先，否则用全局传入的）
    has_any_wts = bool(word_ts) or any(s.get("word_ts") for s in scenes)
    if not has_any_wts:
        return []  # 无任何词级时间戳 → 不做对齐校验（避免在缺数据时误报）

    early = early_frames / fps
    errors = []

    for i, scene in enumerate(scenes):
        ts = scene["timeline_start"]
        n = scene.get("n", i + 1)
        # 开场首 scene 豁免（可在首词前起片）
        if scene.get("section") == "intro" and ts == 0.0:
            continue
        if ts == 0.0:
            continue

        # 该 scene 自己的 word_ts 优先；否则用全片 word_ts
        wts = scene.get("word_ts") or word_ts
        if not wts:
            errors.append(
                f"scene #{n} timeline_start={ts:.3f}s 无可对齐的 word_ts"
                f"（既无 scene 级也无全片级词级时间戳）"
            )
            continue

        # 找最近的 (word_ts - early) 位置，纯 Python，无 numpy 依赖
        nearest = min(abs(w - early - ts) for w in wts)
        if nearest * 1000 > tolerance_ms:
            errors.append(
                f"scene #{n} timeline_start={ts:.3f}s 距最近词级时间戳"
                f"（含 {early_frames} 帧预入场）{nearest*1000:.1f}ms，超过容差 {tolerance_ms}ms"
                f" -- 视觉切换没卡在念到那一刻（词到失配）"
            )
    return errors


# ---------------------------------------------------------------------------
# ⑧ head-buffer（本项目新增）：source_in 距素材头 >= 3 帧
# ---------------------------------------------------------------------------
def check_head_buffer(
    scenes: list,
    fps: float = DEFAULT_FPS,
    head_buffer_frames: int = HEAD_BUFFER_FRAMES,
) -> list:
    """
    每个 scene 的 source_in 必须距素材头 >= head_buffer_frames 帧。

    why：装配阶段（assemble_edl）用 ffmpeg `-ss` 定位 source_in 时，会回退到最近的
    关键帧（GOP 边界），若 source_in 太贴近素材头（0~2 帧）会出现首帧闪帧 / 黑场。
    留 3 帧 head-buffer 让 -ss 有回退余量，避免观众看到闪帧。

    注意：source_in 恰为 0.0 也判失败（最常见的闪帧来源）。素材头本身就应预留 pad。
    """
    min_in = head_buffer_frames / fps
    errors = []
    for i, scene in enumerate(scenes):
        si = scene["source_in"]
        n = scene.get("n", i + 1)
        if si < min_in:
            errors.append(
                f"scene #{n}：source_in={si:.3f}s 距素材头不足 {head_buffer_frames} 帧"
                f"（需 >= {min_in:.3f}s @ {fps:.0f}fps）-- ffmpeg -ss 回退关键帧会闪帧"
            )
    return errors


# ---------------------------------------------------------------------------
# ⑨ source 文件存在性（本项目新增）：scene.source 指向的分段文件必须真的在盘上
# ---------------------------------------------------------------------------
def check_source_exists(scenes: list, edl_path: Optional[str]) -> list:
    """
    每个 scene.source 解析后必须是磁盘上真实存在的文件。

    why：assemble_edl 拼接时才发现某段缺文件会半途 ffmpeg 失败、留下半成品 tmp；
    前置在此把「EDL 引用了不存在的分段」拦在拼接前。路径解析契约与 assemble_edl
    一致（相对 edl.json 目录），保证「validate 说在、assemble 就找得到」三门统一。

    注意：edl_path 为 None（纯 dict 结构校验，无文件落地的单测）→ 跳过本项
    （由聚合层标记为 skipped，不混进 passed）。
    """
    errors = []
    for i, scene in enumerate(scenes):
        n = scene.get("n", i + 1)
        src = scene["source"]
        resolved = _resolve_source(src, edl_path)
        if not os.path.exists(resolved):
            errors.append(
                f"scene #{n}：分段文件不存在 {src!r}（解析为 {resolved}）"
                f" -- assemble_edl 拼接会半途 ffmpeg 失败"
            )
    return errors


# ---------------------------------------------------------------------------
# 聚合：跑全部 8 项
# ---------------------------------------------------------------------------
def validate_edl(
    edl: dict,
    word_ts: Optional[list] = None,
    total_duration: Optional[float] = None,
    fps: Optional[float] = None,
    align_tolerance_ms: float = 30.0,
    early_frames: int = 2,
    head_buffer_frames: int = HEAD_BUFFER_FRAMES,
    edl_path: Optional[str] = None,
    require_coverage: bool = False,
    require_source_exists: bool = False,
) -> dict:
    """
    跑全部 EDL 校验，返回：
      {
        "passed": bool,
        "errors":  {check_name: [error_str, ...]},   # 实际跑过的项
        "skipped": {check_name: reason_str},          # 因无数据而跳过的项（≠ 通过）
        "summary": "N/M checks passed",               # 只算跑过的项
      }

    word_ts / total_duration 可选 -- 不传则从 edl["metadata"] 取。fps 缺 → 从 metadata 取，再缺 DEFAULT_FPS。

    覆盖（第④项）与 source 存在性（第⑨项）有两态语义，**不再把"无数据"静默当全绿**：
    - total_duration 缺时：require_coverage=False → 记为 skipped（无数据，不混进 passed）；
      require_coverage=True（走多段拼接装配，total_duration 必需）→ 该项判 **fail**「缺 total_duration」。
    - edl_path 缺时：source 存在性无从解析 → 记 skipped；require_source_exists=True（装配模式）
      而 edl_path 仍缺 → fail（装配必须能定位实体文件）。
    - word_ts 缺：第⑦项内部自行跳过返回 []（无数据不阻塞，沿用旧行为）。
    """
    scenes = edl.get("scenes", [])
    meta = edl.get("metadata", {})

    if total_duration is None:
        total_duration = meta.get("total_duration")
    if word_ts is None:
        word_ts = meta.get("word_ts")
    if fps is None:
        fps = meta.get("fps", DEFAULT_FPS)

    results = {}
    skipped: dict = {}
    # 不依赖 timeline_*/音频的结构项总是跑
    results["source_validity"] = check_source_validity(scenes)
    results["source_overlaps"] = check_source_overlaps(scenes)
    results["no_repeats"] = check_no_repeats(scenes)
    results["head_buffer"] = check_head_buffer(scenes, fps=fps,
                                               head_buffer_frames=head_buffer_frames)

    # contiguity / source_ordering 需要 timeline_* 字段（完整 EDL 才有）
    if scenes and "timeline_start" in scenes[0]:
        results["contiguity"] = check_contiguity(scenes)
        results["source_ordering"] = check_source_ordering(scenes)
    else:
        skipped["contiguity"] = "无 timeline_start 字段（非完整装配 EDL）"
        skipped["source_ordering"] = "无 timeline_start 字段（非完整装配 EDL）"

    # 词级对齐（缺 word_ts 时函数内部自行跳过返回 []）
    results["wordts_alignment"] = check_wordts_alignment(
        scenes, word_ts=word_ts, fps=fps,
        tolerance_ms=align_tolerance_ms, early_frames=early_frames,
    )

    # ④ 覆盖整片：缺 total_duration 不再静默全绿
    if total_duration is not None:
        results["coverage"] = check_coverage(scenes, total_duration)
    elif require_coverage:
        results["coverage"] = [
            "走多段拼接装配但缺 total_duration（metadata.total_duration 或 --total），"
            "无法校验末尾 scene 是否盖满整片 -- 装配模式 total_duration 必需"
        ]
    else:
        skipped["coverage"] = "无 total_duration（metadata 与 --total 均缺）"

    # ⑨ source 文件存在性：edl_path 缺则无从解析实体路径
    if edl_path is not None:
        results["source_exists"] = check_source_exists(scenes, edl_path)
    elif require_source_exists:
        results["source_exists"] = [
            "走多段拼接装配但未提供 edl_path，无法解析 / 校验 scene.source 实体文件是否存在"
        ]
    else:
        skipped["source_exists"] = "未提供 edl_path（纯结构校验，不落地文件）"

    all_errors = [e for errs in results.values() for e in errs]
    n_checks = len(results)
    n_failed = sum(1 for errs in results.values() if errs)

    return {
        "passed": len(all_errors) == 0,
        "errors": results,
        "skipped": skipped,
        "summary": f"{n_checks - n_failed}/{n_checks} checks passed",
    }


def assert_valid_edl(
    edl: dict,
    word_ts: Optional[list] = None,
    total_duration: Optional[float] = None,
    **kwargs,
) -> None:
    """校验不过则抛 AssertionError，附带完整报告。出片管线 / pytest 用。"""
    result = validate_edl(edl, word_ts=word_ts, total_duration=total_duration, **kwargs)
    if not result["passed"]:
        lines = [f"EDL 校验未通过 -- {result['summary']}"]
        for check, errors in result["errors"].items():
            for e in errors:
                lines.append(f"  [{check}] {e}")
        raise AssertionError("\n".join(lines))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _main(argv: list) -> int:
    import argparse

    # Windows 默认 GBK 控制台无法打印 ✅/❌ 等字符 → 强制 stdout/stderr 走 UTF-8
    # （等价于 PYTHONUTF8=1，但内置进脚本，免去调用方设环境变量）
    for stream in (sys.stdout, sys.stderr):
        reconfig = getattr(stream, "reconfigure", None)
        if reconfig is not None:
            try:
                reconfig(encoding="utf-8")
            except (ValueError, OSError):
                pass

    parser = argparse.ArgumentParser(
        description="sansheng-video EDL 校验器（8 项机检，preview 硬验收前置）",
    )
    parser.add_argument("edl", help="EDL JSON 文件路径")
    parser.add_argument("--fps", type=float, default=None,
                        help=f"帧率（默认读 metadata.fps，再缺用 {DEFAULT_FPS}）")
    parser.add_argument("--total", type=float, default=None,
                        help="整片总时长（秒），默认读 metadata.total_duration")
    parser.add_argument("--tolerance-ms", type=float, default=30.0,
                        help="word_ts 卡点对齐容差（ms），默认 30")
    parser.add_argument("--head-buffer-frames", type=int, default=HEAD_BUFFER_FRAMES,
                        help=f"head-buffer 帧数，默认 {HEAD_BUFFER_FRAMES}")
    parser.add_argument("--assemble", action="store_true",
                        help="装配模式：total_duration / source 实体文件视为必需（缺则判 fail，不再静默跳过）")
    args = parser.parse_args(argv)

    try:
        with open(args.edl, "r", encoding="utf-8") as f:
            edl = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"❌ 读取 EDL 失败：{e}", file=sys.stderr)
        return 2

    result = validate_edl(
        edl,
        total_duration=args.total,
        fps=args.fps,
        align_tolerance_ms=args.tolerance_ms,
        head_buffer_frames=args.head_buffer_frames,
        edl_path=args.edl,                       # source 存在性按 edl.json 所在目录解析
        require_coverage=args.assemble,
        require_source_exists=args.assemble,
    )

    print(f"EDL：{args.edl}")
    n_ran = len(result["errors"])
    print(f"结果：{result['summary']}（跑了 {n_ran} 项）")

    # 跳过项单列：区分「跳过(无数据)」与「通过」，不再把无数据混进全绿
    if result["skipped"]:
        print(f"⏭️  跳过 {len(result['skipped'])} 项（无数据，未校验，不计入通过）：")
        for check, reason in result["skipped"].items():
            print(f"  [{check}] {reason}")

    if result["passed"]:
        print(f"✅ 跑过的 {n_ran} 项全部通过 -- 可进 preview 人眼硬验收")
        return 0

    print("❌ 存在问题：")
    for check, errors in result["errors"].items():
        for e in errors:
            print(f"  [{check}] {e}")
    return 1


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
