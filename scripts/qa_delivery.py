#!/usr/bin/env python3
"""成片测量适配器：把本仓 timeline.json 翻译给 vendor 的 qa_video.py，并按本仓口径出中文结论。

用法：
  python3 scripts/qa_delivery.py final.mp4 [--timeline timeline.json] [--platform douyin|shipinhao|xhs|…]
                                 [--out qa/] [--profile-dir 目录] [--json]

vendor 脚本只通过子进程调用，不 import、不修改。响度是否达标由本脚本自己判定；
冻结段与切点只给提示。退出码：1 = 响度不达标；2 = vendor 没有生成 report.json 或输入有误；其余 0。
适配器只用标准库（numpy、Pillow 只由 vendor 使用）。
"""
import argparse
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "scripts" / "vendor" / "video-director" / "qa_video.py"

DEFAULT_LUFS = -14.0          # 没有 profile 时的目标：主流短视频平台的常见整合响度
DEFAULT_TRUE_PEAK_MAX = -1.0  # 真峰值上限：AAC 编码会抬高峰值，留 1 dB 余量防削波
LOUDNESS_TOLERANCE_LU = 1.0   # ±1 LU：平台响度归一的常见容差，见 references/craft-defaults.md
HOLD_OVERLAP_RATIO = 0.5      # 与 reads 重叠达到冻结段一半以上 = 设计停留
REVIEW_SECS = 3.0             # 非设计停留且 >= 3 秒 = 待查
CUT_MERGE_FRAMES = 2          # 相邻间隔 <= 2 帧的检出切点合并为一次
CUT_MATCH_FRAMES = 3          # 与计划切点相差在 3 帧以内算对上
_NON_PLATFORM_KEYS = {"true_peak_max", "normalize_true_peak", "default"}


# ---------------------------------------------------------------- 目标解析

def load_profile(profile_dir=None):
    sys.path.insert(0, str(ROOT))
    from setup import profile  # setup.py 的 main 受 __name__ 保护，import 不会执行
    return profile(profile_dir)


def resolve_targets(configuration, platform=None):
    """返回 {platform, target_lufs, true_peak_max, source}。"""
    loud = {}
    if isinstance(configuration, dict):
        delivery = configuration.get("delivery")
        if isinstance(delivery, dict) and isinstance(delivery.get("loudness"), dict):
            loud = delivery["loudness"]

    def num(key):
        v = loud.get(key)
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    tp = num("true_peak_max")
    tp = DEFAULT_TRUE_PEAK_MAX if tp is None else tp
    if platform and platform not in _NON_PLATFORM_KEYS and num(platform) is not None:
        return {"platform": platform, "target_lufs": num(platform), "true_peak_max": tp,
                "source": f"profile 平台 {platform}"}
    if num("default") is not None:
        why = f"平台 {platform} 不在 profile 中，" if platform else "未指定平台，"
        return {"platform": platform, "target_lufs": num("default"), "true_peak_max": tp,
                "source": why + "使用 profile 的 default"}
    return {"platform": platform, "target_lufs": DEFAULT_LUFS, "true_peak_max": tp,
            "source": "无 profile 响度配置，使用默认 -14 LUFS"}


def judge_loudness(measured_lufs, measured_tp, target, tp_max):
    """返回 (是否达标, 原因列表)。"""
    reasons = []
    if measured_lufs is None or not math.isfinite(measured_lufs):
        reasons.append("整合响度无法测得（可能全程无声）")
    elif abs(measured_lufs - target) > LOUDNESS_TOLERANCE_LU:
        reasons.append(f"整合响度 {measured_lufs:.1f} LUFS 偏离目标 {target:g} 超过 ±{LOUDNESS_TOLERANCE_LU:g} LU")
    if measured_tp is not None and measured_tp > tp_max:
        reasons.append(f"真峰值 {measured_tp:.1f} dBTP 高于上限 {tp_max:g}")
    return (not reasons), reasons


# ---------------------------------------------------------------- 时间线翻译

def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def read_plan(timeline):
    """从本仓 timeline 取出计划切点、节拍、安静区间、reads 区间。"""
    shots = [s for s in timeline.get("shots", []) if isinstance(s, dict)
             and _num(s.get("start")) is not None and _num(s.get("end")) is not None]
    shots.sort(key=lambda s: s["start"])
    end = max((float(s["end"]) for s in shots), default=0.0)
    bounds = sorted({float(v) for s in shots for v in (s["start"], s["end"])
                     if v > 1e-6 and v < end - 1e-6})
    beats = sorted({float(s["start"]) for s in shots})
    by_id = {s.get("id"): s for s in shots}
    quiet = []
    for d in timeline.get("sound_design", []) or []:
        if isinstance(d, dict) and d.get("mode") == "quiet":
            for sid in d.get("scene_ids", []) or []:
                s = by_id.get(sid)
                if s:
                    quiet.append({"from": float(s["start"]), "to": float(s["end"])})
    quiet.sort(key=lambda q: q["from"])
    reads = []
    for s in shots:
        for r in s.get("reads", []) or []:
            a, b = _num(r.get("start")), _num(r.get("end"))
            if a is not None and b is not None and b > a:
                reads.append((a, b))
    reads.sort()
    return {"cuts": bounds, "beats": beats, "quiet": quiet, "reads": reads,
            "requires_audio": timeline.get("requires_audio") is True}


def vendor_timeline(plan):
    return {"scenes": [{"id": f"shot{i}", "start": b} for i, b in enumerate(plan["beats"])],
            "cuts": plan["cuts"], "silences": plan["quiet"]}


# ---------------------------------------------------------------- 冻结段与切点

def _overlap(a, b, reads):
    """[a,b] 与 reads 并集的重叠长度。"""
    merged = []
    for s, e in sorted(reads):
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return sum(max(0.0, min(b, e) - max(a, s)) for s, e in merged)


def classify_frozen(frozen, reads):
    out = {"design_hold": [], "review": [], "short_pause": []}
    for fr in frozen:
        a, b = float(fr["from"]), float(fr["to"])
        length = b - a
        item = {"from": a, "to": b, "secs": round(length, 2), "to_end": bool(fr.get("to_end"))}
        if length > 0 and _overlap(a, b, reads) >= HOLD_OVERLAP_RATIO * length - 1e-9:
            out["design_hold"].append(item)
        elif length >= REVIEW_SECS:
            out["review"].append(item)
        else:
            out["short_pause"].append(item)
    return out


def merge_cuts(cuts, fps):
    """相邻间隔 <= 2 帧的合并为一次，取这一串的第一个时刻。"""
    gap = CUT_MERGE_FRAMES / fps + 1e-3
    merged = []
    last = None
    for t in sorted(float(c) for c in cuts):
        if last is not None and t - last <= gap:
            last = t
            continue
        merged.append(t)
        last = t
    return merged


def compare_cuts(detected, planned, fps):
    tol = CUT_MATCH_FRAMES / fps + 1e-3
    free = list(detected)
    matched, missing = [], []
    for p in planned:
        near = min(free, key=lambda c: abs(c - p), default=None)
        if near is not None and abs(near - p) <= tol:
            matched.append({"planned": p, "detected": near, "err_frames": round((near - p) * fps, 2)})
            free.remove(near)
        else:
            missing.append(p)
    return {"matched": matched, "missing": missing, "extra": free}


# ---------------------------------------------------------------- 主流程

def _fmt_range(item):
    tail = "（到片尾）" if item.get("to_end") else ""
    return f"{item['from']:.2f}–{item['to']:.2f} 秒（{item['secs']:.2f} 秒）{tail}"


def _jnum(v):
    if isinstance(v, float) and not math.isfinite(v):
        return str(v)
    return v


def build_summary_md(s):
    L = ["# 成片测量摘要", "", f"文件：{s['video']}", ""]
    ld = s["loudness"]
    L += ["## 平台与响度目标", ""]
    L.append(f"- 平台：{s['platform'] or '未指定'}；目标 {ld['target_lufs']:g} LUFS（±{LOUDNESS_TOLERANCE_LU:g} LU），"
             f"真峰值上限 {ld['true_peak_max']:g} dBTP（{ld['source']}）")
    if ld["measured_lufs"] is None and ld["measured_true_peak"] is None:
        L.append("- 实测：成片没有音轨，未测响度" + ("" if not ld["ok"] else "（无声作品，不判不达标）"))
    else:
        L.append(f"- 实测：整合响度 {ld['measured_lufs']} LUFS，真峰值 {ld['measured_true_peak']} dBTP")
    L.append("- 结论：" + ("响度达标" if ld["ok"] else "响度不达标：" + "；".join(ld["reasons"])))
    if s.get("planned_silences"):
        bad = [p for p in s["planned_silences"] if not p.get("ok")]
        L.append(f"- 计划安静段：共 {len(s['planned_silences'])} 段，{len(bad)} 段实际不够安静（提示）")
    L += ["", "## 冻结段", ""]
    fz = s["frozen"]
    for key, title in (("design_hold", "设计停留（落在 reads 区间内）"),
                       ("review", "待查（不在 reads 内且 ≥3 秒）"),
                       ("short_pause", "短停顿（仅供参考）")):
        L.append(f"- {title}：" + ("无" if not fz[key] else "；".join(_fmt_range(i) for i in fz[key])))
    L += ["", "## 切点比对", ""]
    c = s["cuts"]
    if c["planned"] is None:
        L.append(f"- 未提供时间线，不比对计划切点。检出切点（合并后）：{c['detected'] or '无'}")
    else:
        L.append(f"- 计划 {len(c['planned'])} 个，检出（合并后）{len(c['detected'])} 个，对上 {len(c['matched'])} 个")
        L.append("- 缺失（计划有、成片没检出）：" + (", ".join(f"{t:.2f}" for t in c["missing"]) or "无"))
        L.append("- 多出（成片检出、计划没有）：" + (", ".join(f"{t:.2f}" for t in c["extra"]) or "无"))
        L.append("- 以上均为提示，不影响退出码")
    L += ["", "## 联系表", ""]
    uses = {"hook": "0–3 秒每 0.5 秒一帧，看静音开头能不能看懂这是什么、要做什么",
            "phone": "每秒一帧缩成手机宽度，看字在手机上是否看得清",
            "beats": "每个节拍点后取一帧，逐段看每段画面"}
    for k in ("hook", "phone", "beats"):
        L.append(f"- {s['sheets'].get(k) or '（未生成）'}：{uses[k]}")
    L += ["", f"原始报告：{s['report_md']}、{s['report_json']}", ""]
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--timeline")
    ap.add_argument("--platform")
    ap.add_argument("--out", default="qa")
    ap.add_argument("--profile-dir")
    ap.add_argument("--json", action="store_true", help="标准输出打印 summary.json")
    args = ap.parse_args(argv)

    video = Path(args.video)
    if not video.is_file():
        print(f"找不到成片：{video}", file=sys.stderr)
        return 2
    try:
        prof = load_profile(args.profile_dir)
    except (OSError, ValueError) as exc:
        print(f"profile 读取失败：{exc}", file=sys.stderr)
        return 2
    targets = resolve_targets(prof["configuration"] if prof else None, args.platform)

    plan = None
    if args.timeline:
        try:
            plan = read_plan(json.loads(Path(args.timeline).read_text()))
        except (OSError, ValueError) as exc:
            print(f"时间线读取失败：{exc}", file=sys.stderr)
            return 2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for stale in ("report.json", "report.md"):
        (out / stale).unlink(missing_ok=True)

    with tempfile.TemporaryDirectory(prefix="qa_delivery_") as tmp:
        cmd = [sys.executable, str(VENDOR), str(video), "--out", str(out),
               "--lufs", str(targets["target_lufs"]), "--tp", str(targets["true_peak_max"])]
        if plan:
            tl = Path(tmp) / "timeline.json"
            tl.write_text(json.dumps(vendor_timeline(plan)))
            cmd += ["--beats", str(tl)]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                              errors="replace")
    rj = out / "report.json"
    if not rj.is_file():
        tail = "\n".join(proc.stderr.strip().splitlines()[-15:])
        print("vendor 没有生成 report.json，测量失败。stderr 末尾：\n" + tail, file=sys.stderr)
        return 2
    report = json.loads(rj.read_text())

    fps = float(report["info"]["fps"])
    aud = report.get("audio")
    lufs = aud.get("lufs") if aud else None
    tp = aud.get("true_peak") if aud else None
    if aud is None:
        # 无音轨只有在时间线声明有声时才是缺陷；无声作品照常通过。
        if plan and plan["requires_audio"]:
            ok, reasons = False, ["时间线声明有声（requires_audio: true），成片却没有音轨"]
        else:
            ok, reasons = True, []
    else:
        ok, reasons = judge_loudness(lufs, tp, targets["target_lufs"], targets["true_peak_max"])

    reads = plan["reads"] if plan else []
    frozen = classify_frozen(report["picture"]["frozen"], reads)
    detected = merge_cuts(report["picture"]["cuts"], fps)
    cuts = {"detected": detected, "planned": plan["cuts"] if plan else None,
            "matched": [], "missing": [], "extra": []}
    if plan:
        cuts.update(compare_cuts(detected, plan["cuts"], fps))

    summary = {
        "video": str(video), "platform": args.platform, "fps": fps,
        "loudness": {**targets, "tolerance_lu": LOUDNESS_TOLERANCE_LU,
                     "measured_lufs": _jnum(lufs), "measured_true_peak": _jnum(tp),
                     "ok": ok, "reasons": reasons},
        "frozen": frozen, "cuts": cuts,
        "planned_silences": (aud or {}).get("planned_silences", []),
        "sheets": report.get("sheets", {}),
        "report_md": str(out / "report.md"), "report_json": str(rj),
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    md = build_summary_md(summary)
    (out / "summary.md").write_text(md)
    print(json.dumps(summary, ensure_ascii=False, indent=2) if args.json else md)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
