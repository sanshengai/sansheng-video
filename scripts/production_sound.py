"""Scene sound decisions and pre-encode wiring checks, not listening approval.

Decisions share the existing shot IDs and event clock. This is the explicit
HTML adapter's contract; other assemblers must validate their own real tracks.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from urllib.parse import unquote, urlsplit

from generate_sfx_tags import Composition, digest, find_manifest, plan, probe_audio
from production_sound_review import plan as review_plan, current_plan


def decisions(timeline, *, required=False):
    """Validate design if present; legacy export is still allowed, not designed."""
    rows = timeline.get("sound_design")
    if rows is None and "sound_design" not in timeline:
        if required and timeline.get("requires_audio"):
            raise ValueError("sound_design missing: decide source, supplement or quiet in the existing timeline")
        return None
    if not isinstance(rows, list) or not rows:
        raise ValueError("sound_design must be a nonempty list; an empty plan is not deliberate quiet")
    shots = {shot["id"]: shot for shot in timeline["shots"]}
    cues = {key: [] for key in shots}
    for event in timeline["events"]:
        if "sound" in event:
            cues[event["scene_id"]].append(event)
    covered = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) - {"scene_ids", "mode", "reason", "source_elements"}:
            raise ValueError("unsupported sound_design fields")
        scene_ids = row.get("scene_ids")
        if (not isinstance(scene_ids, list) or not scene_ids
                or any(not isinstance(s, str) or s not in shots for s in scene_ids)
                or len(set(scene_ids)) != len(scene_ids) or covered.intersection(scene_ids)):
            raise ValueError("sound_design has missing, duplicate or unknown scene IDs")
        covered.update(scene_ids)
        mode, reason = row.get("mode"), row.get("reason")
        if mode not in {"source", "supplement", "quiet"}:
            raise ValueError("sound_design.mode must be source, supplement or quiet")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("sound_design requires the scene-specific reason")
        sources = row.get("source_elements", [])
        if (not isinstance(sources, list) or any(not isinstance(s, str) or not s.strip() for s in sources)
                or len(set(sources)) != len(sources)):
            raise ValueError("source_elements must contain unique media element IDs")
        if mode == "source" and not sources:
            raise ValueError("source decision requires actual source_elements")
        if mode == "quiet" and sources:
            raise ValueError("quiet cannot promise retained scene sound")
        for scene in scene_ids:
            if mode == "supplement":
                if not cues[scene] or not timeline["requires_audio"]:
                    raise ValueError(f"{scene}: supplement decision has no sound event")
                if any(event["sound"].get("volume", .45) <= 0 for event in cues[scene]):
                    raise ValueError(f"{scene}: planned sound has zero volume")
            elif cues[scene]:
                raise ValueError(f"{scene}: sound events conflict with {mode}; choose supplement")
        if sources and not timeline["requires_audio"]:
            raise ValueError("retained sound conflicts with requires_audio=false")
    if covered != set(shots):
        raise ValueError("sound_design does not cover every scene")
    return rows


def _finite(value, label, *, positive=False):
    try:
        result = float(value)
    except (ValueError, TypeError):
        raise ValueError(label + ": expected explicit finite number") from None
    if not math.isfinite(result) or result < 0 or (positive and result == 0):
        raise ValueError(label + ": invalid value")
    return result


def _bound(path, inputs, label):
    path = path.resolve()
    if not path.is_file() or not path.stat().st_size or inputs.get(str(path)) != digest(path):
        raise ValueError(label + " missing, changed or absent from production dependencies: " + str(path))
    return path


def preflight(project, timeline, build):
    """Follow decisions to actual locked HTML media before calling the encoder."""
    project = Path(project).resolve()
    rows = decisions(timeline, required=True)
    # Export can inspect legacy plans. New renders need a declared local intent
    # for each added cue, so a quiet detail is not judged as a key action.
    expected_review = review_plan(timeline, require_intent=True)
    actual_review, review_sha = current_plan(project / "derived/production-build.json")
    if actual_review != expected_review:
        raise ValueError("sound review plan differs from the render source")
    index = _bound(project / "index.html", build["inputs"], "HTML")
    cues_path = project / "derived/sound-cues.json"
    cues = json.loads(cues_path.read_text())
    # Check the current derived cue list, even if a caller bypassed export.
    expected = [{**event["sound"], "id": event["id"], "scene_id": event["scene_id"], "time": event["start"]}
                for event in sorted(timeline["events"], key=lambda e: (e["start"], e["id"])) if "sound" in event]
    if cues != expected:
        raise ValueError("sound cues differ from the existing timeline")
    comp = Composition(index.read_text())
    if abs(comp.duration - timeline["duration"]) > 1e-6:
        raise ValueError("sound consumer composition duration differs from timeline")
    if cues:
        lock = _bound(find_manifest(index), build["inputs"], "asset lock")
        raw, updated, _, wired = plan(index, lock, cues_path)
        if raw != updated:
            raise ValueError("planned sounds are not wired into HTML; apply current generate_sfx_tags output and re-export")
        for cue in wired:
            if cue["volume"] <= 0:
                raise ValueError("planned sound has zero volume")
            _bound(project / cue["src"], build["inputs"], "sound asset")
    elif any("data-sfx-auto" in item[1] for item in comp.media_elements):
        raise ValueError("HTML contains sound cues absent from the timeline")
    retained = []
    for row in rows or []:
        intervals = []
        for ident in row.get("source_elements", []):
            if ident not in comp.media:
                raise ValueError("retained source media element missing: " + ident)
            _, attrs, inside = comp.media[ident]
            if not inside or "muted" in attrs or "data-sfx-auto" in attrs:
                raise ValueError("retained source is outside composition, muted or a supplemental cue: " + ident)
            src = attrs.get("src", "")
            url = urlsplit(src)
            if not src or url.scheme or url.netloc or url.query or url.fragment or "\\" in src:
                raise ValueError("retained source must be a project-local media file: " + ident)
            path = (project / unquote(url.path)).resolve()
            if not path.is_relative_to(project):
                raise ValueError("retained source path escapes project: " + ident)
            _bound(path, build["inputs"], "retained source")
            media_duration = probe_audio(path)
            start = _finite(attrs.get("data-start"), ident + ".data-start")
            duration = _finite(attrs.get("data-duration"), ident + ".data-duration", positive=True)
            offset = _finite(attrs.get("data-playback-start", attrs.get("data-media-start", "0")), ident + ".source offset")
            rate = _finite(attrs.get("data-playback-rate", "1"), ident + ".playback rate", positive=True)
            _finite(attrs.get("data-volume", "1"), ident + ".volume", positive=True)
            if rate != 1:
                raise ValueError("preprocess retained sound speed before this adapter: " + ident)
            if offset + duration > media_duration + .001 or start + duration > comp.duration + .001:
                raise ValueError("retained source interval exceeds media or composition: " + ident)
            intervals.append((start, start + duration))
            retained.append(ident)
        # Source decisions must actually cover each named scene, not touch it at one instant.
        if intervals:
            for scene in row["scene_ids"]:
                shot = next(s for s in timeline["shots"] if s["id"] == scene)
                cursor = shot["start"]
                for start, end in sorted(intervals):
                    if start > cursor + 1e-6:
                        break
                    cursor = max(cursor, end)
                if cursor < shot["end"] - 1e-6:
                    raise ValueError("retained source does not cover scene: " + scene)
    return {"status": "wired_not_listened", "decisions": len(rows or []),
            "supplemental_cues": len(cues), "retained_elements": sorted(set(retained)),
            "design_sha256": hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest(),
            "review_plan_sha256": review_sha}
