#!/usr/bin/env python3
"""Resolve a promotion brief into the existing production event export."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


def text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}: expected nonempty text")
    return value


def indexed(rows, label):
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"{label}: expected nonempty list")
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"{label}: expected objects")
        ident = text(row.get("id"), f"{label}.id")
        if ident in result:
            raise ValueError(f"{label}: duplicate id {ident}")
        result[ident] = row
    return result


def resolve(source, timeline):
    """Return resolved data and fingerprints; local captures establish provenance, not truth."""
    source = Path(source).resolve()
    raw = source.read_bytes()
    brief = json.loads(raw)
    if not isinstance(brief, dict) or brief.get("kind") != "promotion-brief/1":
        raise ValueError("expected promotion-brief/1")
    if brief.get("mode") not in {"showcase", "walkthrough", "mixed"}:
        raise ValueError("promotion mode: showcase, walkthrough or mixed")
    for key in ("audience", "promise", "title", "destination"):
        text(brief.get(key), key)
    if brief["mode"] == "mixed" and brief.get("primary") not in {"showcase", "walkthrough"}:
        raise ValueError("mixed promotion requires primary")
    evidence = indexed(brief.get("evidence"), "evidence")
    claims = indexed(brief.get("claims"), "claims")
    fingerprints = {str(source): hashlib.sha256(raw).hexdigest()}
    resolved = []
    for ident, row in evidence.items():
        media = (source.parent / text(row.get("file"), f"{ident}.file")).resolve()
        if not media.is_file() or not media.stat().st_size:
            raise ValueError(f"{ident}: missing or empty evidence {media}")
        checksum = hashlib.sha256(media.read_bytes()).hexdigest()
        if row.get("sha256") != checksum:
            raise ValueError(f"{ident}: evidence fingerprint mismatch")
        text(row.get("version"), f"{ident}.version")
        timestamp = datetime.fromisoformat(text(row.get("acquired_at"), f"{ident}.acquired_at").replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError(f"{ident}: acquired_at requires timezone")
        if "url" in row:
            url = urlparse(text(row["url"], f"{ident}.url"))
            if url.scheme not in {"http", "https"} or not url.netloc:
                raise ValueError(f"{ident}: invalid source URL")
        fingerprints[str(media)] = checksum
        extra = {}
        if row.get("kind") == "web-walkthrough":
            import web_walkthrough
            extra["walkthrough"], capture_inputs = web_walkthrough.resolve(media)
            fingerprints.update(capture_inputs)
            fingerprints[str(Path(web_walkthrough.__file__).resolve())] = hashlib.sha256(Path(web_walkthrough.__file__).read_bytes()).hexdigest()
        resolved.append({**row, "file": str(media), **extra})
    for ident, row in claims.items():
        text(row.get("benefit"), f"{ident}.benefit")
        refs = row.get("evidence_ids")
        if not isinstance(refs, list) or not refs or any(not isinstance(i, str) or i not in evidence for i in refs):
            raise ValueError(f"{ident}: missing or unknown evidence_ids")
    used = set()
    links = []
    for event in timeline["events"]:
        refs = event.get("claim_ids", [])
        if not isinstance(refs, list) or any(not isinstance(i, str) or i not in claims for i in refs):
            raise ValueError(f"{event['id']}: unknown claim_ids")
        if refs and "visual" not in event:
            raise ValueError(f"{event['id']}: claim needs a visual consumer")
        used.update(refs)
        if refs:
            links.append({"event_id": event["id"], "scene_id": event["scene_id"],
                          "start": event["start"], "end": event["end"], "claim_ids": refs})
    if used != set(claims):
        raise ValueError("claims without visual events: " + ", ".join(sorted(set(claims) - used)))
    return {**brief, "evidence": resolved, "event_links": links,
            "status": "source_bound_not_fact_or_aesthetic_approval"}, fingerprints
