"""
sansheng-video EDL 校验 pytest -- 覆盖 validate_edl.py 全部 8 项的通过/失败用例。

fixture 仿上游 tests/test_edl_validation.py 的 _make_cut/_minimal_edl，
转译为 _make_scene/_minimal_edl（cuts→scenes、source_file→source、beats→word_ts）。

跑法（脚本目录下）：
    pytest test_edl_validation.py -v
或从 skill 根：
    pytest tests/test_edl_validation.py -v
"""

import copy
import json
import os
import sys

import pytest

# 让 pytest 从任意 cwd 都能 import 同目录的 validate_edl
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from validate_edl import (  # noqa: E402
    check_contiguity,
    check_source_ordering,
    check_source_validity,
    check_coverage,
    check_no_repeats,
    check_source_overlaps,
    check_wordts_alignment,
    check_head_buffer,
    check_source_exists,
    validate_edl,
    assert_valid_edl,
    DEFAULT_FPS,
    HEAD_BUFFER_FRAMES,
)
from check_merge_compat import distinct_sources_from_edl  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers（仿上游 _make_cut / _minimal_edl）
# ---------------------------------------------------------------------------

def _make_scene(n, ts, te, source="hf/ch01.html", si=1.0, so=None,
                section="body", voiceover="测试口播句", word_ts=None):
    """构造一个合法 scene；source_in 默认 1.0（已满足 head-buffer）。"""
    so = so if so is not None else si + (te - ts)
    return {
        "n": n,
        "timeline_start": ts,
        "timeline_end": te,
        "source": source,
        "source_in": si,
        "source_out": so,
        "section": section,
        "voiceover": voiceover,
        "word_ts": word_ts,
    }


def _minimal_edl(scenes, total_duration=10.0, word_ts=None, fps=DEFAULT_FPS):
    return {
        "metadata": {
            "total_duration": total_duration,
            "fps": fps,
            "word_ts": word_ts,
        },
        "audio_file": "视频稿/narration.wav",
        "output_file": "成片.mp4",
        "scenes": scenes,
    }


@pytest.fixture
def clean_edl():
    """三 scene 首尾相接、覆盖满 6.0s、source_in 均 >= head-buffer 的干净 EDL。"""
    scenes = [
        _make_scene(1, ts=0.0, te=2.0, section="intro", si=0.5, so=2.5),
        _make_scene(2, ts=2.0, te=4.0, source="录屏/clip-a.mp4", si=1.0, so=3.0),
        _make_scene(3, ts=4.0, te=6.0, source="broll/veo-01.mp4", si=2.0, so=4.0),
    ]
    return _minimal_edl(scenes, total_duration=6.0)


# ---------------------------------------------------------------------------
# ① 时间线连续
# ---------------------------------------------------------------------------

class TestContiguity:
    def test_contiguous_passes(self):
        scenes = [
            _make_scene(1, ts=0.0, te=2.0),
            _make_scene(2, ts=2.0, te=5.0),
            _make_scene(3, ts=5.0, te=8.0),
        ]
        assert check_contiguity(scenes) == []

    def test_gap_fails(self):
        scenes = [
            _make_scene(1, ts=0.0, te=2.0),
            _make_scene(2, ts=2.5, te=5.0),  # 500ms 空洞
        ]
        errors = check_contiguity(scenes)
        assert errors
        assert "2" in errors[0]

    def test_overlap_fails(self):
        scenes = [
            _make_scene(1, ts=0.0, te=3.0),
            _make_scene(2, ts=2.5, te=5.0),  # 500ms 重叠
        ]
        assert check_contiguity(scenes)

    def test_single_scene_passes(self):
        assert check_contiguity([_make_scene(1, ts=0.0, te=5.0)]) == []


# ---------------------------------------------------------------------------
# ② 顺序非递减
# ---------------------------------------------------------------------------

class TestSourceOrdering:
    def test_forward_ordering_passes(self):
        scenes = [
            _make_scene(1, ts=0.0, te=2.0, si=1.0, so=3.0),
            _make_scene(2, ts=2.0, te=4.0, si=3.0, so=5.0),
            _make_scene(3, ts=4.0, te=6.0, si=5.0, so=7.0),
        ]
        assert check_source_ordering(scenes) == []

    def test_backward_ordering_fails(self):
        scenes = [
            _make_scene(1, ts=0.0, te=2.0, si=5.0, so=7.0),
            _make_scene(2, ts=2.0, te=4.0, si=3.0, so=5.0),  # 倒带
        ]
        assert check_source_ordering(scenes)

    def test_equal_source_in_ok(self):
        scenes = [
            _make_scene(1, ts=0.0, te=2.0, si=1.0, so=3.0),
            _make_scene(2, ts=2.0, te=4.0, si=3.0, so=5.0),  # 恰在 high-water
        ]
        assert check_source_ordering(scenes) == []

    def test_different_sources_independent(self):
        scenes = [
            _make_scene(1, ts=0.0, te=2.0, source="a.mp4", si=5.0, so=7.0),
            _make_scene(2, ts=2.0, te=4.0, source="b.mp4", si=1.0, so=3.0),
            _make_scene(3, ts=4.0, te=6.0, source="a.mp4", si=7.0, so=9.0),
        ]
        assert check_source_ordering(scenes) == []


# ---------------------------------------------------------------------------
# ③ source 区间合法
# ---------------------------------------------------------------------------

class TestSourceValidity:
    def test_valid_passes(self):
        assert check_source_validity([_make_scene(1, ts=0.0, te=2.0, si=0.5, so=2.5)]) == []

    def test_source_out_lte_source_in_fails(self):
        assert check_source_validity([_make_scene(1, ts=0.0, te=2.0, si=3.0, so=2.0)])

    def test_negative_source_in_fails(self):
        errors = check_source_validity([_make_scene(1, ts=0.0, te=2.0, si=-0.5, so=1.5)],
                                       min_source_in=0.0)
        assert errors


# ---------------------------------------------------------------------------
# ④ 覆盖整片
# ---------------------------------------------------------------------------

class TestCoverage:
    def test_exact_coverage_passes(self):
        assert check_coverage([_make_scene(1, ts=0.0, te=30.0)], total_duration=30.0) == []

    def test_within_tolerance_passes(self):
        assert check_coverage([_make_scene(1, ts=0.0, te=29.8)],
                              total_duration=30.0, tolerance_s=0.5) == []

    def test_large_gap_fails(self):
        assert check_coverage([_make_scene(1, ts=0.0, te=25.0)], total_duration=30.0)

    def test_empty_scenes_fails(self):
        assert check_coverage([], total_duration=30.0)


# ---------------------------------------------------------------------------
# ⑤ 精确去重
# ---------------------------------------------------------------------------

class TestNoRepeats:
    def test_unique_passes(self):
        scenes = [
            _make_scene(1, ts=0.0, te=2.0, si=1.0),
            _make_scene(2, ts=2.0, te=4.0, si=3.0),
        ]
        assert check_no_repeats(scenes) == []

    def test_repeated_source_in_fails(self):
        scenes = [
            _make_scene(1, ts=0.0, te=2.0, si=1.0),
            _make_scene(2, ts=2.0, te=4.0, si=1.0),  # 同 source 同 in
        ]
        assert check_no_repeats(scenes)

    def test_same_in_different_source_passes(self):
        scenes = [
            _make_scene(1, ts=0.0, te=2.0, source="a.mp4", si=1.0),
            _make_scene(2, ts=2.0, te=4.0, source="b.mp4", si=1.0),
        ]
        assert check_no_repeats(scenes) == []


# ---------------------------------------------------------------------------
# ⑥ 区间重叠
# ---------------------------------------------------------------------------

class TestSourceOverlaps:
    def test_no_overlap_passes(self):
        scenes = [
            _make_scene(1, ts=0.0, te=2.0, source="a.mp4", si=1.0, so=3.0),
            _make_scene(2, ts=2.0, te=4.0, source="a.mp4", si=3.0, so=5.0),  # 紧邻不重叠
        ]
        assert check_source_overlaps(scenes) == []

    def test_overlap_fails(self):
        scenes = [
            _make_scene(1, ts=0.0, te=2.0, source="a.mp4", si=1.0, so=4.0),
            _make_scene(2, ts=2.0, te=4.0, source="a.mp4", si=3.0, so=6.0),  # 3~4 重叠
        ]
        errors = check_source_overlaps(scenes)
        assert errors
        assert "重叠" in errors[0]

    def test_overlap_detected_regardless_of_edl_order(self):
        """EDL 顺序乱放，重叠仍被排序扫描抓到。"""
        scenes = [
            _make_scene(1, ts=0.0, te=2.0, source="a.mp4", si=5.0, so=8.0),
            _make_scene(2, ts=2.0, te=4.0, source="a.mp4", si=6.0, so=9.0),  # 6~8 重叠
        ]
        assert check_source_overlaps(scenes)

    def test_different_sources_no_false_positive(self):
        scenes = [
            _make_scene(1, ts=0.0, te=2.0, source="a.mp4", si=1.0, so=5.0),
            _make_scene(2, ts=2.0, te=4.0, source="b.mp4", si=1.0, so=5.0),  # 不同 source
        ]
        assert check_source_overlaps(scenes) == []


# ---------------------------------------------------------------------------
# ⑦ 卡点对齐（word_ts）
# ---------------------------------------------------------------------------

class TestWordtsAlignment:
    def test_perfect_snap_passes(self):
        # word_ts 每 0.5s 一个词；early = 2/30
        word_ts = [0.5 * i for i in range(1, 21)]
        early = 2 / DEFAULT_FPS
        scenes = [
            _make_scene(1, ts=round(word_ts[0] - early, 3), te=round(word_ts[4] - early, 3),
                        section="intro"),
            _make_scene(2, ts=round(word_ts[4] - early, 3), te=round(word_ts[8] - early, 3)),
        ]
        assert check_wordts_alignment(scenes, word_ts=word_ts) == []

    def test_large_offset_fails(self):
        word_ts = [0.5 * i for i in range(1, 21)]
        early = 2 / DEFAULT_FPS
        # 故意比词级时间戳晚 200ms
        scenes = [_make_scene(1, ts=round(word_ts[0] - early + 0.200, 3), te=2.0)]
        assert check_wordts_alignment(scenes, word_ts=word_ts, tolerance_ms=30.0)

    def test_timeline_start_zero_exempt(self):
        word_ts = [1.0, 2.0, 3.0]
        scenes = [_make_scene(1, ts=0.0, te=0.917, section="intro")]
        assert check_wordts_alignment(scenes, word_ts=word_ts) == []

    def test_off_word_fails(self):
        word_ts = [0.5 * i for i in range(1, 21)]
        early = 2 / DEFAULT_FPS
        off = round(word_ts[2] - early + 0.150, 3)  # 落在两词中间
        scenes = [_make_scene(1, ts=off, te=3.0)]
        assert check_wordts_alignment(scenes, word_ts=word_ts, tolerance_ms=30.0)

    def test_scene_level_word_ts_used(self):
        """scene 自带 word_ts 时优先于全片 word_ts。"""
        early = 2 / DEFAULT_FPS
        scenes = [
            _make_scene(1, ts=0.0, te=1.0, section="intro"),
            _make_scene(2, ts=round(2.0 - early, 3), te=3.0, word_ts=[2.0, 2.5]),
        ]
        # 不传全片 word_ts，仅靠 scene 级
        assert check_wordts_alignment(scenes) == []

    def test_no_word_ts_skips(self):
        """完全没有词级时间戳 → 跳过，不报错（无数据不阻塞）。"""
        scenes = [
            _make_scene(1, ts=0.0, te=2.0),
            _make_scene(2, ts=2.0, te=4.0),
        ]
        assert check_wordts_alignment(scenes, word_ts=None) == []


# ---------------------------------------------------------------------------
# ⑧ head-buffer（本项目新增）
# ---------------------------------------------------------------------------

class TestHeadBuffer:
    def test_sufficient_buffer_passes(self):
        # 1.0s >> 3/30 = 0.1s
        assert check_head_buffer([_make_scene(1, ts=0.0, te=2.0, si=1.0, so=3.0)]) == []

    def test_zero_source_in_fails(self):
        """source_in 恰为 0.0 是最常见闪帧来源，必须拦。"""
        errors = check_head_buffer([_make_scene(1, ts=0.0, te=2.0, si=0.0, so=2.0)])
        assert errors
        assert "闪帧" in errors[0]

    def test_just_under_buffer_fails(self):
        # 2/30 < 3/30 边界下
        fps = 30.0
        si = 2 / fps
        errors = check_head_buffer([_make_scene(1, ts=0.0, te=2.0, si=si, so=2.0)], fps=fps)
        assert errors

    def test_exactly_buffer_passes(self):
        fps = 30.0
        si = HEAD_BUFFER_FRAMES / fps  # 恰好 3 帧
        assert check_head_buffer([_make_scene(1, ts=0.0, te=2.0, si=si, so=2.0)], fps=fps) == []

    def test_fps_scales_threshold(self):
        """高帧率下 3 帧对应更短秒数，原本失败的 source_in 可能通过。"""
        si = 0.06  # 60ms：24fps 下 <3 帧(0.125s) 失败；60fps 下 3 帧=0.05s 通过
        assert check_head_buffer([_make_scene(1, ts=0.0, te=2.0, si=si, so=2.0)], fps=24.0)
        assert check_head_buffer([_make_scene(1, ts=0.0, te=2.0, si=si, so=2.0)], fps=60.0) == []


# ---------------------------------------------------------------------------
# validate_edl / assert_valid_edl 聚合
# ---------------------------------------------------------------------------

class TestValidateEdl:
    def test_clean_edl_passes(self, clean_edl):
        result = validate_edl(clean_edl)
        assert result["passed"], (
            "干净 EDL 不该失败：\n"
            + "\n".join(f"  [{k}] {e}"
                        for k, errs in result["errors"].items() for e in errs)
        )

    def test_assert_valid_passes_on_clean(self, clean_edl):
        assert_valid_edl(clean_edl)

    def test_assert_valid_raises_on_gap(self, clean_edl):
        broken = copy.deepcopy(clean_edl)
        broken["scenes"][1]["timeline_start"] += 0.5  # 造空洞
        with pytest.raises(AssertionError, match="contiguity"):
            assert_valid_edl(broken)

    def test_assert_valid_raises_on_head_buffer(self, clean_edl):
        broken = copy.deepcopy(clean_edl)
        broken["scenes"][0]["source_in"] = 0.0  # 贴素材头
        with pytest.raises(AssertionError, match="head_buffer"):
            assert_valid_edl(broken)

    def test_without_word_ts_skips_alignment(self, clean_edl):
        # clean_edl 的 metadata.word_ts 为 None → 对齐项返回 []（不缺项，只是空）
        result = validate_edl(clean_edl)
        assert result["errors"]["wordts_alignment"] == []

    def test_word_ts_from_metadata_used(self):
        early = 2 / DEFAULT_FPS
        scenes = [
            _make_scene(1, ts=0.0, te=2.0, section="intro", si=0.5, so=2.5),
            _make_scene(2, ts=round(2.0 - early, 3), te=4.0, source="b.mp4", si=1.0, so=3.0),
        ]
        edl = _minimal_edl(scenes, total_duration=4.0,
                           word_ts=[0.5 * i for i in range(1, 11)])
        # timeline_end 末尾盖满 4.0，对齐命中 metadata.word_ts
        result = validate_edl(edl)
        assert result["errors"]["wordts_alignment"] == []

    def test_coverage_skipped_without_total(self):
        scenes = [_make_scene(1, ts=0.0, te=5.0)]
        edl = {"metadata": {}, "scenes": scenes}  # 无 total_duration
        result = validate_edl(edl)
        assert "coverage" not in result["errors"]

    def test_summary_format(self, clean_edl):
        result = validate_edl(clean_edl)
        assert "/" in result["summary"]
        assert "passed" in result["summary"]

    def test_overlap_caught_in_aggregate(self, clean_edl):
        broken = copy.deepcopy(clean_edl)
        # scene2 与新增 scene 同 source 重叠
        broken["scenes"][1]["source_out"] = 5.0  # clip-a.mp4 1.0~5.0
        broken["scenes"].append(
            _make_scene(4, ts=6.0, te=8.0, source="录屏/clip-a.mp4", si=2.0, so=4.0)
        )
        broken["metadata"]["total_duration"] = 8.0
        result = validate_edl(broken)
        assert not result["passed"]
        assert result["errors"]["source_overlaps"]


# ---------------------------------------------------------------------------
# ⑨ source 文件存在性 + 路径解析契约（本项目新增回归）
# ---------------------------------------------------------------------------

def _write_edl_with_real_sources(base_dir, *, total_duration=6.0, source_names=None):
    """
    在 base_dir 下落地一个真实可拼接的 EDL：
      - <base_dir>/视频稿/edl.json
      - <base_dir>/视频稿/seg/<name>.mp4 （空文件，仅测存在性/路径解析，不 probe）
    scene.source 用相对 edl.json 目录的相对路径，验证「相对 edl.json 解析」契约。
    返回 edl.json 的绝对路径。
    """
    src_names = source_names or ["seg/seg-01.mp4", "seg/seg-02.mp4", "seg/seg-03.mp4"]
    edl_dir = os.path.join(base_dir, "视频稿")
    os.makedirs(os.path.join(edl_dir, "seg"), exist_ok=True)
    for name in src_names:
        fp = os.path.join(edl_dir, *name.split("/"))
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "wb") as f:
            f.write(b"")  # 空占位文件，只测存在性 / 路径解析

    scenes = []
    seg = total_duration / len(src_names)
    for i, name in enumerate(src_names):
        ts = round(i * seg, 3)
        te = round((i + 1) * seg, 3)
        scenes.append(_make_scene(i + 1, ts=ts, te=te, source=name, si=1.0, so=1.0 + seg))

    edl = {
        "metadata": {"total_duration": total_duration, "fps": DEFAULT_FPS},
        "audio_file": "narration.wav",
        "output_file": "成片.mp4",
        "scenes": scenes,
    }
    edl_path = os.path.join(edl_dir, "edl.json")
    with open(edl_path, "w", encoding="utf-8") as f:
        json.dump(edl, f, ensure_ascii=False)
    return edl_path


class TestSourceExistsPathContract:
    def test_resolves_relative_to_edl_not_cwd(self, tmp_path, monkeypatch):
        """① 从非「视频稿」目录跑：source 相对 edl.json 目录仍命中（不靠 cwd）。"""
        edl_path = _write_edl_with_real_sources(str(tmp_path))
        with open(edl_path, encoding="utf-8") as f:
            edl = json.load(f)

        # 故意把 cwd 切到一个跟 edl.json 完全无关的目录
        other = tmp_path / "somewhere_else"
        other.mkdir()
        monkeypatch.chdir(other)

        # 相对 cwd 解析会全部找不到；相对 edl.json 目录解析全部命中
        assert check_source_exists(edl["scenes"], edl_path) == []

    def test_missing_source_file_fails(self, tmp_path):
        """source 指向不存在的文件 → 判 fail（带「不存在」字样）。"""
        edl_path = _write_edl_with_real_sources(str(tmp_path))
        with open(edl_path, encoding="utf-8") as f:
            edl = json.load(f)
        edl["scenes"][1]["source"] = "seg/不存在.mp4"
        errors = check_source_exists(edl["scenes"], edl_path)
        assert errors
        assert "不存在" in errors[0]

    def test_source_in_dir_with_spaces_not_false_negative(self, tmp_path, monkeypatch):
        """② source 落在含空格目录里 → 整条路径作单元素解析，不再假失败。"""
        spaced = tmp_path / "my project dir"  # 路径含空格
        spaced.mkdir()
        edl_path = _write_edl_with_real_sources(str(spaced))
        with open(edl_path, encoding="utf-8") as f:
            edl = json.load(f)

        monkeypatch.chdir(tmp_path)  # 再从别处跑
        assert check_source_exists(edl["scenes"], edl_path) == []

        # check_merge_compat 抽 source 也得拿到含空格的整条路径（不被 xargs 式拆切）
        srcs = distinct_sources_from_edl(edl_path)
        assert len(srcs) == 3
        assert all(os.path.exists(s) for s in srcs), srcs
        assert all(" " in s for s in srcs), "含空格路径必须整条保留"

    def test_distinct_sources_dedup_and_order(self, tmp_path):
        """check_merge_compat 抽 source：去重 + 按首次出现顺序。"""
        edl_path = _write_edl_with_real_sources(
            str(tmp_path),
            source_names=["seg/a.mp4", "seg/b.mp4", "seg/a.mp4"],  # a 重复
        )
        srcs = distinct_sources_from_edl(edl_path)
        # 3 个 scene 但只 2 个 distinct source（a 去重），顺序 a 在 b 前
        assert len(srcs) == 2
        assert srcs[0].endswith(os.path.join("seg", "a.mp4"))
        assert srcs[1].endswith(os.path.join("seg", "b.mp4"))


# ---------------------------------------------------------------------------
# 覆盖检查两态：装配模式下缺 total_duration 不再 8/8 全绿（本项目新增回归）
# ---------------------------------------------------------------------------

class TestCoverageRequiredInAssemble:
    def test_missing_total_skipped_not_passed_by_default(self):
        """非装配模式：缺 total_duration → 记 skipped（不混进 errors，也不是「通过」）。"""
        scenes = [_make_scene(1, ts=0.0, te=5.0)]
        edl = {"metadata": {}, "scenes": scenes}  # 无 total_duration
        result = validate_edl(edl)
        assert "coverage" not in result["errors"]          # 没跑
        assert "coverage" in result["skipped"]              # 明确标记为跳过
        # summary 只算跑过的项，不把跳过当通过
        assert "coverage" not in result["summary"]

    def test_missing_total_fails_in_assemble_mode(self):
        """③ 装配模式（require_coverage=True）漏写 total_duration → coverage 判 fail，非 8/8 全绿。"""
        scenes = [_make_scene(1, ts=0.0, te=5.0)]
        edl = {"metadata": {}, "scenes": scenes}  # 漏写 total_duration
        result = validate_edl(edl, require_coverage=True)
        assert not result["passed"], "装配模式缺 total_duration 必须判失败，不许全绿放行"
        assert result["errors"].get("coverage"), "coverage 应报缺项"
        assert "total_duration" in result["errors"]["coverage"][0]

    def test_present_total_still_runs_coverage(self):
        """有 total_duration 时装配模式照常跑 coverage（不误伤正常 EDL）。"""
        scenes = [_make_scene(1, ts=0.0, te=6.0)]
        edl = {"metadata": {"total_duration": 6.0}, "scenes": scenes}
        result = validate_edl(edl, require_coverage=True)
        assert result["errors"].get("coverage") == []
        assert "coverage" not in result["skipped"]

    def test_assert_valid_raises_on_missing_total_in_assemble(self):
        """assert_valid_edl 在装配模式下，缺 total_duration 直接抛 AssertionError。"""
        scenes = [_make_scene(1, ts=0.0, te=5.0)]
        edl = {"metadata": {}, "scenes": scenes}
        with pytest.raises(AssertionError, match="coverage"):
            assert_valid_edl(edl, require_coverage=True)

    def test_source_exists_skipped_without_edl_path(self):
        """无 edl_path（纯 dict 校验）→ source_exists 记 skipped，不误判失败。"""
        scenes = [_make_scene(1, ts=0.0, te=6.0)]
        edl = {"metadata": {"total_duration": 6.0}, "scenes": scenes}
        result = validate_edl(edl)  # 不传 edl_path
        assert "source_exists" not in result["errors"]
        assert "source_exists" in result["skipped"]
