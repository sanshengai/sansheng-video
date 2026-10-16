#!/usr/bin/env python3
"""Import existing production block anchors; no TTS, ASR, approval or rendering."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(label + ": expected finite number")
    return value


def validate_blocks(text, blocks, duration):
    """Validate production chunks without claiming word timing or listening."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("empty narration text")
    if not isinstance(blocks, list) or not blocks:
        raise ValueError("missing narration blocks")
    previous_end = 0
    for block in blocks:
        if not isinstance(block, dict) or not isinstance(block.get("text"), str) or not block["text"].strip():
            raise ValueError("empty narration block")
        start = number(block.get("at"), "block.at")
        length = number(block.get("duration"), "block.duration")
        if start < 0 or length <= 0 or start + length > duration + .001:
            raise ValueError("block outside audio duration")
        if start < previous_end - .001:
            raise ValueError("overlapping or unordered narration blocks")
        previous_end = start + length
    if "".join(block["text"] for block in blocks) != text:
        raise ValueError("narration text does not match complete blocks")


def probe_duration(audio):
    run = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "format=duration:stream=codec_type", "-of", "json", str(audio)],
                         capture_output=True, text=True, check=True, timeout=30)
    data = json.loads(run.stdout)
    if not any(stream.get("codec_type") == "audio" for stream in data.get("streams", [])):
        raise ValueError("narration contains no audio stream")
    duration = float(data["format"]["duration"])
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("invalid actual audio duration")
    return duration


def find_audio(value, audio, base):
    matches = []
    if isinstance(value, dict):
        if isinstance(value.get("path"), str) and "chunks" in value and "text" in value:
            if (base / value["path"]).resolve() == audio:
                matches.append(value)
        for item in value.values():
            matches.extend(find_audio(item, audio, base))
    elif isinstance(value, list):
        for item in value:
            matches.extend(find_audio(item, audio, base))
    return matches


def import_evidence(record_path, audio_path):
    """Bind one unique existing audio/chunks record to its actual local bytes.

    Relative audio paths inside the source record resolve against that record.
    Inputs are read only; returned evidence can be stored by the caller.
    """
    record_path, audio = Path(record_path).resolve(), Path(audio_path).resolve()
    source_bytes = record_path.read_bytes()
    source_hash = hashlib.sha256(source_bytes).hexdigest()
    audio_hash = digest(audio)
    matches = find_audio(json.loads(source_bytes), audio, record_path.parent)
    if len(matches) != 1:
        raise ValueError("source record must uniquely identify the selected audio")
    selected = matches[0]
    if selected.get("sha256") != audio_hash:
        raise ValueError("audio SHA256 differs from original production record")
    duration = probe_duration(audio)
    recorded_duration = number(selected.get("duration"), "recorded duration")
    if abs(duration - recorded_duration) > .002:
        raise ValueError("actual audio duration differs from production record")
    chunks = selected.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        raise ValueError("missing narration blocks")
    blocks = [{key: block.get(key) for key in ("text", "at", "duration")}
              if isinstance(block, dict) else block for block in chunks]
    validate_blocks(selected.get("text"), blocks, duration)
    if digest(record_path) != source_hash or digest(audio) != audio_hash:
        raise ValueError("narration inputs changed during import")
    return {"kind": "production-narration-blocks/1", "source_record": str(record_path),
            "source_record_sha256": source_hash, "audio_path": str(audio), "audio_sha256": audio_hash,
            "duration": duration, "recorded_duration": recorded_duration,
            "text": selected["text"], "blocks": blocks,
            "anchor_basis": "existing_production_block_offsets",
            "limitations": ["Block-level production anchors only; not word alignment",
                            "No new ASR or listening review performed",
                            "No rights clearance or human approval inferred"]}


def verify_evidence(evidence_path):
    """Revalidate all evidence against current record, audio bytes and duration."""
    path = Path(evidence_path).resolve()
    evidence_bytes = path.read_bytes()
    evidence_hash = hashlib.sha256(evidence_bytes).hexdigest()
    value = json.loads(evidence_bytes)
    if value.get("kind") != "production-narration-blocks/1":
        raise ValueError("unknown narration evidence")
    validate_blocks(value.get("text"), value.get("blocks"), number(value.get("duration"), "duration"))
    actual = import_evidence(value["source_record"], value["audio_path"])
    if value != actual:
        raise ValueError("narration evidence differs from original production record or audio")
    if digest(path) != evidence_hash:
        raise ValueError("narration evidence changed during verification")
    return actual


def verified_inputs(evidence_path):
    """Return validated blocks and the exact dependencies used to validate them."""
    evidence_path = Path(evidence_path).resolve()
    importer = Path(__file__).resolve()
    initial = {str(evidence_path): digest(evidence_path), str(importer): digest(importer)}
    value = verify_evidence(evidence_path)
    expected = {**initial, value["source_record"]: value["source_record_sha256"],
                value["audio_path"]: value["audio_sha256"]}
    for path, fingerprint in expected.items():
        if digest(path) != fingerprint:
            raise ValueError("narration input changed after verification: " + path)
    return value, expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    add = commands.add_parser("import")
    add.add_argument("--record", required=True, type=Path)
    add.add_argument("--audio", required=True, type=Path)
    add.add_argument("--out", required=True, type=Path)
    check = commands.add_parser("check")
    check.add_argument("evidence", type=Path)
    args = parser.parse_args()
    if args.command == "check":
        value = verify_evidence(args.evidence)
        print(json.dumps({"kind": value["kind"], "duration": value["duration"],
                          "blocks_checked": len(value["blocks"])}, ensure_ascii=False))
    else:
        if args.out.exists() or args.out.is_symlink():
            raise ValueError("evidence output already exists; use a new path")
        if args.out.resolve() in {args.record.resolve(), args.audio.resolve()}:
            raise ValueError("evidence cannot overwrite an input")
        value = import_evidence(args.record, args.audio)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        print(str(args.out.resolve()))


if __name__ == "__main__":
    main()
