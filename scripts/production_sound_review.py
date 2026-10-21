"""Derive listening windows from the production clock; never approve hearing.

The plan is an index into the final exported movie, not a second sound timeline
or an audibility detector. Component measurements belong to the real assembler
and may help a listener; this module has no universal level/gain thresholds.
"""
from __future__ import annotations

import hashlib
import html
import json
import math
import os
from pathlib import Path
from urllib.parse import quote


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def intent(event, *, required=False):
    value = event.get("sound_intent")
    if value is None and "sound_intent" not in event:
        if required and "sound" in event:
            raise ValueError(event["id"] + ": sound_intent missing; declare role, prominence and reason")
        return None
    if (not isinstance(value, dict) or set(value) - {"role", "prominence", "reason", "music_duck"}
            or value.get("role") not in {"dialogue", "music", "ambience", "action"}
            or value.get("prominence") not in {"key", "support", "distant"}
            or not isinstance(value.get("reason"), str) or not value["reason"].strip()):
        raise ValueError(event["id"] + ": invalid sound_intent; use role/prominence/scene-specific reason")
    if "music_duck" in value:
        duck = value["music_duck"]
        if (not isinstance(duck, dict) or set(duck) != {"factor", "attack", "release"}
                or value["role"] == "music"
                or any(isinstance(duck[k], bool) or not isinstance(duck[k], (int, float))
                       or not math.isfinite(duck[k]) for k in duck)
                or not 0 <= duck["factor"] < 1 or duck["attack"] <= 0 or duck["release"] <= 0):
            raise ValueError(event["id"] + ": music_duck needs explicit factor [0,1), positive attack/release and a non-music target")
    return value


def plan(timeline, *, require_intent=False):
    """No new timestamps: scene intervals and cue/action times come from source."""
    modes = {scene: row for row in timeline.get("sound_design", [])
             for scene in row["scene_ids"]}
    items = []
    for shot in timeline["shots"]:
        row = modes.get(shot["id"], {})
        items.append({"id": "scene:" + shot["id"], "kind": "scene", "scene_id": shot["id"],
                      "start": shot["start"], "end": shot["end"],
                      "mode": row.get("mode", "unspecified"), "reason": row.get("reason", "")})
    for event in sorted(timeline["events"], key=lambda e: (e["start"], e["id"])):
        target = intent(event, required=require_intent)
        if "sound" not in event and target is None:
            continue
        if not timeline["requires_audio"]:
            raise ValueError("sound_intent conflicts with requires_audio=false")
        end = event["start"] + event["sound"]["duration"] if "sound" in event else event["end"]
        items.append({"id": "event:" + event["id"], "kind": "event", "scene_id": event["scene_id"],
                      "start": event["start"], "end": end,
                      # Preview padding only, not a signal-measurement threshold.
                      "context_start": max(0, event["start"] - 1),
                      "context_end": min(timeline["duration"], end + 1),
                      "role": target["role"] if target else "unspecified",
                      "prominence": target["prominence"] if target else "unspecified",
                      "reason": target["reason"] if target else "",
                      **({"music_duck": target["music_duck"]} if target and "music_duck" in target else {})})
    return {"kind": "production-sound-plan/1", "requires_audio": timeline["requires_audio"],
            "duration": timeline["duration"], "items": items}


def current_plan(build_path):
    """Check the actual derived plan against the source owned by this build."""
    build_path = Path(build_path).resolve()
    build = json.loads(build_path.read_text())
    source = build.get("source")
    path = build_path.parent / "sound-review-plan.json"
    if not isinstance(source, str) or source not in build.get("inputs", {}):
        raise ValueError("sound review needs a current export with an explicit source; re-export the timeline")
    if not Path(source).is_file() or digest(source) != build["inputs"][source]:
        raise ValueError("sound review source changed")
    if not path.is_file() or build.get("outputs", {}).get(path.name) != digest(path):
        raise ValueError("sound review plan missing or stale; re-export the timeline")
    actual = json.loads(path.read_text())
    if actual != plan(json.loads(Path(source).read_text())):
        raise ValueError("sound review plan differs from the existing timeline")
    return actual, digest(path)


CHECKS = ("dialogue_clarity", "level_relationships", "naturalness", "action_sync", "transients")


def pending(plan_data, plan_sha256, output_sha256):
    """A template can only be pending. Callers must not infer listening results."""
    return {"kind": "production-sound-listening/1", "status": "pending",
            "plan_sha256": plan_sha256, "output_sha256": output_sha256,
            "listener": None, "playback": None,
            "checks": {key: "pending" for key in CHECKS}, "not_applicable_reason": {},
            "items": [{"id": item["id"], "outcome": "pending", "note": ""} for item in plan_data["items"]]}


def verify_listening(review, plan_data, plan_sha256, output_sha256):
    """Verify explicit evidence/coverage, not whether a person actually heard it."""
    audio = review.get("audio_review")
    if (not isinstance(audio, dict) or audio.get("kind") != "production-sound-listening/1"
            or audio.get("status") != "listened"):
        raise ValueError("final mix listening is pending; technical checks do not approve audibility")
    if audio.get("plan_sha256") != plan_sha256 or audio.get("output_sha256") != output_sha256:
        raise ValueError("listening record does not match the current final mix and sound plan")
    for key in ("listener", "playback"):
        if not isinstance(audio.get(key), str) or not audio[key].strip():
            raise ValueError("listening requires actual listener and playback context")
    checks = audio.get("checks")
    if not isinstance(checks, dict) or set(checks) != set(CHECKS):
        raise ValueError("listening checks incomplete")
    for key, result in checks.items():
        if result == "not_applicable" and key in {"dialogue_clarity", "action_sync"}:
            reasons = audio.get("not_applicable_reason")
            reason = reasons.get(key) if isinstance(reasons, dict) else None
            if not isinstance(reason, str) or not reason.strip():
                raise ValueError("not_applicable listening check needs a reason")
        elif result != "pass":
            raise ValueError("final listening check not accepted: " + key)
    rows = audio.get("items")
    expected = {item["id"]: item for item in plan_data["items"]}
    if (not isinstance(rows, list) or len(rows) != len(expected)
            or any(not isinstance(row, dict) or row.get("id") not in expected for row in rows)
            or len({row["id"] for row in rows}) != len(expected)):
        raise ValueError("listening does not cover every planned scene and sound event")
    for row in rows:
        item = expected[row["id"]]
        allowed = {"appropriate"} if item["kind"] == "scene" else {"clear"}
        if item.get("prominence") in {"support", "distant"}:
            allowed.add("intentionally_subtle")
        if row.get("outcome") not in allowed:
            raise ValueError("sound window still needs review: " + row["id"])
        if not isinstance(row.get("note"), str) or not row["note"].strip():
            raise ValueError("sound window needs the actual local listening observation: " + row["id"])
    return {"status": "listening_record_bound_not_independently_heard", "windows": len(rows)}


def listening_page(output, page, plan_data):
    """Seek/play only the final movie. No standalone-asset audition or approval UI."""
    media = quote(os.path.relpath(output, page.parent), safe="/")
    # JSON is inert until parsed; escape script terminators in user-authored text.
    payload = encoded(plan_data).replace("<", "\\u003c")
    buttons = []
    for index, item in enumerate(plan_data["items"]):
        desc = item.get("prominence", item.get("mode", ""))
        buttons.append(f'<li><button data-window="{index}">{html.escape(item["id"])} '
                       f'{item["start"]:g}–{item["end"]:g}s · {html.escape(desc)}</button>'
                       f'<span>{html.escape(item["reason"])}</span></li>')
    return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>最终混音试听</title><style>body{font:16px system-ui;max-width:960px;margin:24px auto;padding:0 16px}'
            'video{width:100%;max-height:55vh;background:#111}button{font:inherit;text-align:left;padding:10px;cursor:pointer}'
            'li{margin:12px 0}span{display:block;color:#555;overflow-wrap:anywhere}ul{padding-left:20px}</style>'
            '<h1>最终混音试听 · 待验</h1><p>对白先作基准；听关键动作是否清楚、背景是否平滑避让、动作同步、自然度与瞬态是否刺耳。'
            '远处细节及有意留白按剧情判断。点击窗口只播放最终文件，不代表试听通过。</p>'
            f'<video controls preload="metadata" src="{html.escape(media, quote=True)}"></video>'
            '<button id="full">播放全片</button><ul>' + ''.join(buttons) + '</ul>'
            f'<script type="application/json" id="plan">{payload}</script>'
            '<script>const v=document.querySelector("video"),p=JSON.parse(document.querySelector("#plan").textContent);'
            'let stop=null;v.addEventListener("timeupdate",()=>{if(stop!==null&&v.currentTime>=stop){v.pause();stop=null;}});'
            'document.querySelectorAll("[data-window]").forEach(b=>b.onclick=()=>{const x=p.items[Number(b.dataset.window)];'
            'stop=x.context_end??x.end;v.currentTime=x.context_start??x.start;v.play().catch(()=>{});});'
            'document.querySelector("#full").onclick=()=>{stop=null;v.currentTime=0;v.play().catch(()=>{});};</script></html>')
