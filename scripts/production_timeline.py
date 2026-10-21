#!/usr/bin/env python3
"""Export shared production events; no renderer, alignment claims or approval.

Retains the motion-review plan's fps/duration/canvas/shots shape. Events add
optional caption/visual/sound consumers. All times are absolute seconds.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from motion_review_schedule import schedule
import production_narration
import promotion
import select_assets
from production_sound import decisions as sound_decisions
from production_sound_review import plan as sound_review_plan


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"


def nonempty(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}: expected nonempty text")
    return value


def number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label}: expected finite number")
    return value


def validate(timeline, narration=None):
    if not isinstance(timeline, dict):
        raise ValueError("timeline must be an object")
    # Reuse existing contiguous-shot, frame and reading-window semantics.
    review = {key: timeline[key] for key in ("fps", "duration", "canvas", "shots")}
    if "direction" in timeline:
        review["direction"] = timeline["direction"]
    schedule(review)
    if type(timeline.get("requires_audio")) is not bool:
        raise ValueError("requires_audio must explicitly be true or false")
    voice = timeline.get("narration")
    offset = 0
    if voice is not None:
        if not isinstance(voice, dict) or set(voice) != {"evidence", "offset"}:
            raise ValueError("narration requires only evidence and offset")
        nonempty(voice.get("evidence"), "narration.evidence")
        offset = number(voice.get("offset"), "narration.offset")
        if not timeline["requires_audio"]:
            raise ValueError("intentional silence conflicts with narration")
        if narration is None:
            raise ValueError("narration requires verified evidence from source-relative export")
        if offset < 0 or offset + narration["duration"] > timeline["duration"] + 1e-9:
            raise ValueError("narration outside timeline")
    shots = {shot["id"]: shot for shot in timeline["shots"]}
    events = timeline.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError("events must be a nonempty list")
    ids = set()
    captions = []
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("event must be an object")
        ident = nonempty(event.get("id"), "event.id")
        if ident in ids:
            raise ValueError("duplicate event id")
        ids.add(ident)
        shot = shots.get(event.get("scene_id"))
        if shot is None:
            raise ValueError(f"{ident}: unknown scene_id")
        start, end = (number(event.get(k), f"{ident}.{k}") for k in ("start", "end"))
        if not shot["start"] <= start < end <= shot["end"]:
            raise ValueError(f"{ident}: event outside its shot")
        basis = event.get("timing_basis")
        if basis not in {"authored", "estimated", "verified_audio"}:
            raise ValueError(f"{ident}: declare timing_basis")
        if basis == "verified_audio":
            if voice is None or narration is None:
                raise ValueError(f"{ident}: missing verified narration evidence")
            index = event.get("narration_block")
            if type(index) is not int or not 0 <= index < len(narration["blocks"]):
                raise ValueError(f"{ident}: invalid narration_block")
            block = narration["blocks"][index]
            expected_start = offset + block["at"]
            if abs(start - expected_start) > 1e-9 or abs(end - (expected_start + block["duration"])) > 1e-9:
                raise ValueError(f"{ident}: narration block time mismatch")
            if "caption" in event and event["caption"] != block["text"]:
                raise ValueError(f"{ident}: narration requires complete block text")
        elif "narration_block" in event:
            raise ValueError(f"{ident}: narration_block requires verified_audio")
        if "timing_evidence" in event:
            raise ValueError("timing_evidence alone is unsupported; use narration evidence and block")
        if not any(key in event for key in ("caption", "visual", "sound")):
            raise ValueError(f"{ident}: no consumer")
        if "caption" in event:
            text = nonempty(event["caption"], f"{ident}.caption")
            if any(x in text for x in ("\n", "\r", "-->", "\x00")):
                raise ValueError("caption must be one plain-text segment")
            a, b = round(start * 1000), round(end * 1000)
            if a >= b:
                raise ValueError("caption collapses at millisecond resolution")
            captions.append((a, b))
        if "visual" in event and (not isinstance(event["visual"], dict) or not event["visual"]):
            raise ValueError("visual must be a nonempty object")
        if "sound" in event:
            if not timeline["requires_audio"]:
                raise ValueError("intentional silence cannot contain sound cues")
            sound = event["sound"]
            if not isinstance(sound, dict):
                raise ValueError("sound must be an object")
            for key in ("asset_id", "revision"):
                nonempty(sound.get(key), f"sound.{key}")
            # Time is owned by the event, never hand-copied into sound.
            if set(sound) - {"asset_id", "revision", "duration", "volume", "track"}:
                raise ValueError("unsupported sound fields; time comes from event.start")
            length = number(sound.get("duration"), "sound.duration")
            if length <= 0 or start + length > end:
                raise ValueError("sound duration outside event")
            volume = number(sound.get("volume", 0.45), "sound.volume")
            if volume < 0:
                raise ValueError("negative sound volume")
            if "track" in sound and (type(sound["track"]) is not int or sound["track"] < 0):
                raise ValueError("sound.track must be nonnegative integer")
    ordered = sorted(captions)
    if any(a[1] > b[0] for a, b in zip(ordered, ordered[1:])):
        raise ValueError("caption intervals overlap")
    sound_decisions(timeline)
    return review


def srt_time(ms):
    seconds, millis = divmod(ms, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02},{millis:03}"


def products(timeline, narration=None, promotion_plan=None, selection_plan=None):
    review = validate(timeline, narration)
    if timeline.get("promotion") is not None and promotion_plan is None:
        raise ValueError("promotion requires source-relative export")
    if any("claim_ids" in event for event in timeline["events"]) and promotion_plan is None:
        raise ValueError("claim_ids require a promotion brief")
    if timeline.get("asset_selection") is not None and selection_plan is None:
        raise ValueError("asset_selection requires source-relative export")
    selected_ids = {item['asset_id'] for item in selection_plan['items']} if selection_plan else set()
    consumed = set()
    for event in timeline['events']:
        ids = (event.get('visual') or {}).get('asset_ids')
        if ids is not None:
            if not isinstance(ids, list) or not ids or any(not isinstance(i, str) or i not in selected_ids for i in ids):
                raise ValueError('visual.asset_ids must reference selected assets')
            consumed.update(ids)
    if selected_ids - consumed:
        raise ValueError('selected assets need visual events: '+', '.join(sorted(selected_ids-consumed)))
    events = sorted(timeline["events"], key=lambda e: (e["start"], e["id"]))
    captions, cues, srt = [], [], []
    for event in events:
        if "caption" in event:
            start, end = round(event["start"] * 1000), round(event["end"] * 1000)
            captions.append({"text": event["caption"], "startMs": start, "endMs": end,
                             "timestampMs": None, "confidence": None,
                             "event_id": event["id"], "timing_basis": event["timing_basis"]})
            srt.append(f"{len(srt)+1}\n{srt_time(start)} --> {srt_time(end)}\n{event['caption']}")
        if "sound" in event:
            cues.append({**event["sound"], "id": event["id"], "scene_id": event["scene_id"],
                         "time": event["start"]})
    # Data only. Consumers seek to the event's absolute start/end in their engine.
    payload = {"fps": timeline["fps"], "duration": timeline["duration"], "events": events}
    if promotion_plan is not None:
        payload["promotion"] = promotion_plan
    if selection_plan is not None:
        payload['asset_selection'] = selection_plan
    if narration is not None:
        payload["narration"] = {"audio_path": narration["audio_path"],
                                "audio_sha256": narration["audio_sha256"],
                                "duration": narration["duration"], "offset": timeline["narration"]["offset"],
                                "anchor_basis": narration["anchor_basis"], "blocks": narration["blocks"]}
    js = encoded(payload)
    js = js.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    outputs = {"events.js": "window.productionTimeline = " + js.rstrip() + ";\n",
            "captions.json": encoded(captions), "captions.srt": "\n\n".join(srt) + ("\n" if srt else ""),
            "sound-cues.json": encoded(cues), "motion-review-plan.json": encoded(review),
            "sound-review-plan.json": encoded(sound_review_plan(timeline))}
    if promotion_plan is not None:
        outputs["promotion-plan.json"] = encoded(promotion_plan)
    if selection_plan is not None:
        outputs['asset-selection.json'] = encoded(selection_plan)
    return outputs


def export(source, destination, dependencies=(), refresh=False):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    source_bytes = source.read_bytes()
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    timeline = json.loads(source_bytes)
    narration, narration_inputs = None, {}
    if timeline.get("narration") is not None:
        voice = timeline["narration"]
        if not isinstance(voice, dict):
            raise ValueError("narration must be an object")
        evidence = nonempty(voice.get("evidence"), "narration.evidence")
        narration, narration_inputs = production_narration.verified_inputs(source.parent / evidence)
    promotion_plan, promotion_inputs = None, {}
    if timeline.get("promotion") is not None:
        brief = nonempty(timeline["promotion"], "promotion")
        promotion_plan, promotion_inputs = promotion.resolve(source.parent / brief, timeline)
    selection_plan, selection_inputs = None, {}
    if timeline.get('asset_selection') is not None:
        selection_path = nonempty(timeline['asset_selection'], 'asset_selection')
        selection_plan, selection_inputs = select_assets.verified(source.parent / selection_path)
        if timeline.get('canvas') != selection_plan['canvas']:
            raise ValueError('timeline and selection canvas differ; make a native selection for this aspect')
    if selection_plan is not None:
        outputs = products(timeline, narration, promotion_plan, selection_plan)
    elif promotion_plan is not None:
        outputs = products(timeline, narration, promotion_plan)
    else:
        outputs = products(timeline, narration) if narration is not None else products(timeline)
    inputs = {source, Path(__file__).resolve(), Path(__file__).with_name("motion_review_schedule.py").resolve()}
    inputs.add(Path(__file__).with_name("production_sound.py").resolve())
    inputs.add(Path(__file__).with_name("production_sound_review.py").resolve())
    inputs.add(Path(__file__).with_name("promotion.py").resolve())
    inputs.update(Path(p).resolve() for p in dependencies)
    inputs.update(Path(p) for p in narration_inputs)
    inputs.update(Path(p) for p in promotion_inputs)
    inputs.update(Path(p) for p in selection_inputs)
    fingerprints = {}
    for path in sorted(inputs):
        if not path.is_file() or not path.stat().st_size:
            raise ValueError(f"missing or empty dependency: {path}")
        fingerprints[str(path)] = digest(path)
    if fingerprints[str(source)] != source_hash:
        raise ValueError("source changed during export; retry from stable input")
    if any(fingerprints[path] != expected for path, expected in narration_inputs.items()):
        raise ValueError("narration input changed after verification")
    if any(fingerprints[path] != expected for path, expected in promotion_inputs.items()):
        raise ValueError("promotion input changed after verification")
    if any(fingerprints[path] != expected for path, expected in selection_inputs.items()):
        raise ValueError('selection input changed after verification')
    names = [*outputs, "production-build.json"]
    if any((destination / name).resolve() in inputs for name in names):
        raise ValueError("outputs would overwrite an input dependency")
    if any((destination / name).is_symlink() for name in names):
        raise ValueError("derived outputs cannot be symlinks")
    if not refresh and any((destination / name).exists() for name in names):
        raise ValueError("derived files exist; use --refresh to regenerate and invalidate old checks")
    destination.mkdir(parents=True, exist_ok=True)
    # Receipt is written last; a partial refresh fails verification against old hashes.
    for name, text in outputs.items():
        (destination / name).write_text(text, encoding="utf-8")
    if any(digest(path) != expected for path, expected in fingerprints.items()):
        raise ValueError("input changed while writing production outputs")
    receipt = {"kind": "production-event-export/1", "status": "compiled_not_rendered", "source": str(source),
               "inputs": fingerprints, "outputs": {name: digest(destination / name) for name in outputs}}
    (destination / "production-build.json").write_text(encoded(receipt))
    return receipt


def check(receipt_path):
    path = Path(receipt_path).resolve()
    receipt = json.loads(path.read_text())
    if receipt.get("kind") != "production-event-export/1" or not receipt.get("inputs") or not receipt.get("outputs"):
        raise ValueError("missing build evidence")
    changed = []
    for name, expected in receipt["inputs"].items():
        target = Path(name)
        if not target.is_file() or digest(target) != expected:
            changed.append(name)
    for name, expected in receipt["outputs"].items():
        target = (path.parent / name).resolve()
        if not target.is_relative_to(path.parent) or not target.is_file() or digest(target) != expected:
            changed.append(name)
    if changed:
        raise ValueError("stale production build: " + ", ".join(changed))
    return {"status": "current_not_reviewed", "inputs": len(receipt["inputs"]), "outputs": len(receipt["outputs"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    build = subs.add_parser("export")
    build.add_argument("source", type=Path)
    build.add_argument("destination", type=Path)
    build.add_argument("--dependency", action="append", default=[], type=Path)
    build.add_argument("--refresh", action="store_true")
    verify = subs.add_parser("check")
    verify.add_argument("receipt", type=Path)
    args = parser.parse_args()
    result = (export(args.source, args.destination, args.dependency, args.refresh)
              if args.command == "export" else check(args.receipt))
    print(encoded(result), end="")


if __name__ == "__main__":
    main()
