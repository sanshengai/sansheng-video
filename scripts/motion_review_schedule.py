#!/usr/bin/env python3
"""Plan diagnostic frames only. No renderer, subprocess, network or media generation."""
import argparse
import hashlib
import json
import math
import sys
from fractions import Fraction


def number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label}: expected a finite number")
    return value


class FrameClock:
    """Half-open intervals; recognize exactly the float produced by n/fps.

    All other times retain their exact binary float value: nextafter neighbours
    are never swallowed by an epsilon. FPS is the declared decimal rate.
    """
    def __init__(self, fps):
        self.fps = fps
        self.rate = Fraction(str(fps))

    def position(self, time):
        product = time * self.fps
        if not math.isfinite(product):
            raise ValueError("frame count product must be finite")
        nearest = round(product)
        if time == nearest / self.fps:
            return Fraction(nearest)
        return Fraction(time) * self.rate

    def ceil(self, time):
        q = self.position(time)
        return -(-q.numerator // q.denominator)

    def nearest(self, time):
        q = self.position(time)
        lower = q.numerator // q.denominator
        return lower if q - lower <= Fraction(1, 2) else lower + 1


def schedule(plan):
    direction = plan.get("direction")
    if direction is not None:
        if not isinstance(direction, dict):
            raise ValueError("direction must be an object")
        for field in ("style_id", "style_version", "purpose"):
            if not isinstance(direction.get(field), str) or not direction[field].strip():
                raise ValueError(f"direction.{field}: expected a nonempty string")
    fps = number(plan["fps"], "fps")
    duration = number(plan["duration"], "duration")
    if fps <= 0 or duration <= 0:
        raise ValueError("fps and duration must be positive")
    limits = plan.get("limits", {})
    if not isinstance(limits, dict):
        raise ValueError("limits must be an object")
    def budget(name, default):
        value = limits.get(name, default)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"limits.{name}: expected a positive integer")
        return value
    max_total = budget("max_total_frames", 1000000)
    max_strips = budget("max_strip_frames", 10000)
    clock = FrameClock(fps)
    total = clock.ceil(duration)
    if total > max_total:
        raise ValueError("total frame budget exceeded")
    strip_count = 0
    canvas = plan["canvas"]
    if not isinstance(canvas, list) or len(canvas) != 2:
        raise ValueError("canvas must contain width and height")
    width, height = [number(v, "canvas") for v in canvas]
    if min(width, height) <= 0 or any(v != int(v) for v in canvas):
        raise ValueError("canvas dimensions must be positive integers")
    # Frame n is evaluated at n/fps. The interval is [0, duration).
    last_frame = total - 1
    records = []
    ids = set()
    previous_end = 0
    previous_final = -1
    shots = plan["shots"]
    if not isinstance(shots, list) or not shots:
        raise ValueError("shots must be a nonempty list")

    def interval(item, label, lo, hi):
        start = number(item["start"], f"{label}.start")
        end = number(item["end"], f"{label}.end")
        if not lo <= start < end <= hi:
            raise ValueError(f"{label}: interval outside [{lo}, {hi}]")
        if not isinstance(item.get("purpose"), str) or not item["purpose"].strip():
            raise ValueError(f"{label}: missing purpose")
        return start, end

    for shot in shots:
        ident = shot["id"]
        if not isinstance(ident, str) or not ident.strip() or ident in ids:
            raise ValueError("shot ids must be unique nonempty strings")
        ids.add(ident)
        start = number(shot["start"], f"{ident}.start")
        end = number(shot["end"], f"{ident}.end")
        if not 0 <= start < end <= duration or start != previous_end:
            raise ValueError(f"{ident}: shots must be ordered, contiguous and within duration")
        previous_end = end
        first = clock.ceil(start)
        final = min(last_frame, clock.ceil(end) - 1)
        if first > final:
            raise ValueError(f"{ident}: no frame exists in this shot")
        # O(1) rolling proof: each ordered half-open shot owns the next frame
        # through its final frame, without materializing a global frame list.
        if first != previous_final + 1:
            raise ValueError(f"{ident}: frame coverage must be contiguous and exactly once")
        previous_final = final
        overview = sorted({first, (first + final) // 2, final})
        read_end = start
        reads = []
        for read in shot.get("reads", []):
            a, b = interval(read, f"{ident}.read", start, end)
            if a < read_end:
                raise ValueError(f"{ident}: important reads overlap or are unordered")
            reveal = number(read["revealCompleteAt"], "revealCompleteAt")
            hold = number(read["min_hold"], "min_hold")
            if not a <= reveal < b or hold < 0 or b - reveal + 1e-8 < hold:
                raise ValueError(f"{ident}: insufficient complete-text reading hold")
            if clock.ceil(reveal) > min(final, clock.ceil(b) - 1):
                raise ValueError(f"{ident}: complete reading window contains no frame")
            read_end = b
            reads.append({"purpose": read["purpose"], "stable_seconds": b - reveal,
                          "check_frame": min(final, clock.ceil(reveal))})
        strips = []
        for window in shot.get("windows", []):
            a, b = interval(window, f"{ident}.window", start, end)
            window_first, window_final = clock.ceil(a), min(final, clock.ceil(b) - 1)
            count = max(0, window_final - window_first + 1)
            if strip_count + count > max_strips:
                raise ValueError("strip frame budget exceeded")
            strip_count += count
            frames = list(range(window_first, window_final + 1))
            if not frames:
                raise ValueError(f"{ident}: action window contains no frame")
            strips.append({"purpose": window["purpose"], "frames": frames})
        crops = []
        for crop in shot.get("crops", []):
            t = number(crop["time"], "crop.time")
            rect = crop["rect"]
            if not isinstance(rect, list) or len(rect) != 4:
                raise ValueError("crop.rect must contain x, y, width, height")
            x, y, w, h = [number(v, "crop.rect") for v in rect]
            if (any(v != int(v) for v in rect) or not start <= t < end or
                    min(x, y) < 0 or min(w, h) <= 0 or x + w > width or y + h > height):
                raise ValueError(f"{ident}: crop outside native canvas or shot")
            if not isinstance(crop.get("purpose"), str) or not crop["purpose"].strip():
                raise ValueError(f"{ident}: crop missing purpose")
            frame = max(first, min(final, clock.nearest(t)))
            actual = frame / fps
            crops.append({"purpose": crop["purpose"], "frame": frame, "rect": rect,
                          "requested_time": t, "actual_time": actual,
                          "quantization_error_seconds": actual - t,
                          "sampling_policy": "nearest_effective_frame_in_shot_ties_earlier"})
        records.append({"id": ident, "overview_frames": overview, "reads": reads,
                        "strips": strips, "native_crops": crops})
    if previous_end != duration:
        raise ValueError("shots must cover the entire duration")
    if previous_final != last_frame:
        raise ValueError("frame coverage must include the final frame exactly once")
    canonical = json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return {"plan_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
            "direction": direction,
            "fps": fps, "duration": duration, "canvas": canvas, "shots": records,
            "frame_coverage": {"first": 0, "last": last_frame, "count": total,
                               "assignment": "exactly_once",
                               "cut_policy": "identical_shared_time_values"},
            "status": "scheduled_only",
            "limitations": ["No media checked", "No audio alignment checked", "No renderer cache validated",
                            "Human playback, readability and age suitability remain required"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan")
    args = parser.parse_args()
    try:
        with open(args.plan, encoding="utf-8") as source:
            result = schedule(json.load(source))
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(f"Invalid review plan: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
