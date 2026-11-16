#!/usr/bin/env python3
"""Cross-field contradiction and bloat linter for AI video generation prompts.

Pure standard library; shared by sansheng-video (assemble_shot_requests.py)
and downstream product pipelines (e.g. batch episode pipelines).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_MAX_WORDS: dict[str, int] = {
    "i2v-still": 100,
    "i2v-action": 120,
    "t2v": 150,
    "r2v-dialogue": 150,
    "legacy": 320,
}

# Strip negated phrases ("no speech, no dialogue", "zero pan, tilt, zoom or dolly")
# while stopping before positive clauses (", riders gallop away", "; at most one...").
_NEG_FRAG = re.compile(
    r"\b(?:no|without|never|nor|zero|not\s+any)\b"
    r"(?:(?!\b(?:and|but|while|whereas|however|then|with|where|which|that|as)\b)[^.;,]){0,60}"
    r"(?:\s*,\s*(?:(?:or|nor|and)\s+)?(?:no\s+|without\s+)?"
    r"(?!(?:a|an|the|his|her|their|some|people|figures|soldiers|riders|men|women|officials)\b)"
    r"(?:[\w'/-]+\s+){0,2}[\w'/-]+){0,6}",
    re.I,
)

NIGHT_LIGHT_RE = re.compile(
    r"\b(?:night|midnight|moonlit|moonlight|dim\s+lamplight|lamplit\s+dark|pitch\s+dark|torchlit\s+night)\b",
    re.I,
)
DUSK_LIGHT_RE = re.compile(r"\b(?:dusk|twilight|sunset|evening\s+sky)\b", re.I)
DAY_LIGHT_RE = re.compile(
    r"\b(?:bright\s+daylight|broad\s+daylight|midday|noon|late\s+morning|early\s+morning|"
    r"morning\s+sun(?:light)?|morning\s+light|afternoon\s+sun(?:light)?|bright\s+sunlight|"
    r"daytime|bright\s+government\s+hall|sunlit\s+(?:morning|afternoon|courtyard|room|hall|desk|table|window))\b",
    re.I,
)

CAM_STATIC_RE = re.compile(
    r"\b(?:locked-off|locked\s+camera|static\s+(?:[\w\-]+\s+){0,2}(?:shot|view)|"
    r"camera\s+remains\s+still|camera\s+does\s+not\s+move|zero\s+(?:camera\s+)?(?:pan|movement|motion))\b",
    re.I,
)
CAM_MOVE_RE = re.compile(
    r"\b(?:push-in|push\s+in|dolly[\s-]+(?:in|out)|pan\s+(?:left|right)|whip\s+pan|"
    r"tilt\s+(?:up|down)|zoom\s+(?:in|out)|tracking\s+(?:shot|camera)|lateral\s+track|"
    r"camera\s+glides?|forward\s+glide|crane\s+(?:up|down|push-in))\b",
    re.I,
)
ACTION_EXIT_RE = re.compile(
    r"\b(?:gallop(?:s|ing)?\s+away|ride(?:s|ing)?\s+away(?:\s+into\s+the\s+distance)?|"
    r"shrink(?:s|ing)?\s+into\s+the\s+distance|walk(?:s|ing)?\s+out\s+of\s+frame|"
    r"disappear(?:s|ing)?\s+into\s+the\s+distance)\b",
    re.I,
)

INDOOR_SCENE_RE = re.compile(
    r"\b(?:indoors|inside\s+a\s+(?:[\w\-]+\s+){0,3}(?:room|hall|chamber|study|palace\s+hall|government\s+hall|longhouse|tent|workshop|temple)|"
    r"dim\s+lamplit\s+room|lamplit\s+room|government\s+hall|palace\s+hall|telegraph\s+relay\s+room)\b",
    re.I,
)
WINDOW_OR_OUTSIDE_RE = re.compile(
    r"\b(?:through\s+(?:the\s+|a\s+)?(?:[\w\-]+\s+){0,2}window|outdoors|outside\s+a\s+|courtyard)\b",
    re.I,
)
OUTDOOR_BLEED_RE = re.compile(
    r"\b(?:dry\s+(?:[\w\-]+\s+){0,2}fields|dirt\s+roads?|villages?|wooden\s+carts?|farmland|open\s+plain|riverbeds?)\b",
    re.I,
)
HUT_BLEED_RE = re.compile(
    r"(?<!inside\s)(?<!inside\sa\s)(?<!inside\sthe\s)\bhuts?\b",
    re.I,
)

VOCAL_TRIGGER_RE = re.compile(
    r"\b(?:speak(?:s|ing)?|talk(?:s|ing)?|convers(?:e|ing|ation)|read(?:s|ing)?\s+aloud|"
    r"shout(?:s|ing)?|distant\s+orders|bark(?:s|ing)?\s+orders|cheer(?:s|ing)?|chant(?:s|ing)?|"
    r"gasp(?:s|ing)?|sigh(?:s|ing)?|whisper(?:s|ing)?|laugh(?:s|ing)?|"
    r"recit(?:e|es|ing)|sing(?:s|ing)?|"
    r"(?<!distant\s)(?<!distant\smarket\s)(?<!distant\scity\s)murmur(?:s|ing)?)\b",
    re.I,
)

BLANK_CARRIER_LOCK_RE = re.compile(
    r"\b(?:no\s+readable\s+(?:writing|text|characters)|blank\s+without\s+writing|"
    r"unmarked\s+surfaces|stays?\s+(?:blurred|blank))\b",
    re.I,
)
READ_WRITE_ACTION_RE = re.compile(
    r"\b(?:reads?\s+(?:from\s+)?(?:the\s+|a\s+|an\s+|his\s+|her\s+)?(?:scroll|bamboo\s+slips?|slips?|tablet|edict|decree|book|letter|inscription)|"
    r"writes?\s+(?:characters|words|text|letters|names?)|"
    r"brushes?\s+(?:ink\s+)?characters|"
    r"carv(?:e|es|ing)\s+(?:characters|words|letters|inscriptions?)|"
    r"points?\s+at\s+(?:the\s+)?(?:characters|writing|inscription|text))\b",
    re.I,
)

MENU_AUDIO_RE = re.compile(r"\b(?:choose\s+from|pick\s+one\s+of|select\s+from)\s*:", re.I)
CUTS_TO_RE = re.compile(r"\bCUTS\s+TO\s*:|\bnext\s+shot\s+starts\b", re.I)
SPEECH_DENY_RE = re.compile(r"\b(?:no\s+speech|no\s+dialogue|no\s+narration|no\s+human\s+vocalizations)\b", re.I)


def strip_negated_clauses(text: str) -> str:
    """Remove negated phrases so 'no speech, no villages' does not self-trigger positive rules."""
    if not text:
        return ""
    return _NEG_FRAG.sub(" ", text)


def _field(shot: dict, *names: str) -> str:
    for name in names:
        val = shot.get(name)
        if isinstance(val, str) and val.strip():
            return val.strip()
        if isinstance(val, (list, tuple)):
            joined = " ".join(str(x).strip() for x in val if str(x).strip())
            if joined:
                return joined
    return ""


def _word_count(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def _check_light_conflict(light_text: str, raw_light_scope: str) -> list[dict]:
    findings: list[dict] = []
    target = light_text or raw_light_scope
    if not target:
        return findings
    has_night = bool(NIGHT_LIGHT_RE.search(target))
    has_dusk = bool(DUSK_LIGHT_RE.search(target))
    has_day = bool(DAY_LIGHT_RE.search(target))
    if (has_night and has_day) or (has_dusk and has_day):
        findings.append({
            "code": "light_conflict",
            "severity": "error",
            "message": "Lighting mixes mutually exclusive time-of-day cues (night/dusk vs daylight/morning).",
        })
        return findings
    if light_text and ";" in light_text:
        clauses = [c.strip() for c in light_text.split(";") if c.strip()]
        if len(clauses) >= 2:
            cats = []
            for c in clauses:
                if NIGHT_LIGHT_RE.search(c):
                    cats.append("night")
                elif DAY_LIGHT_RE.search(c):
                    cats.append("day")
                elif DUSK_LIGHT_RE.search(c):
                    cats.append("dusk")
            if len(set(cats)) > 1:
                findings.append({
                    "code": "light_conflict",
                    "severity": "error",
                    "message": "Light field contains semicolon-separated clauses with conflicting periods.",
                })
    return findings


def lint_shot_prompt(
    shot: dict,
    *,
    mode: str = "i2v-action",
    max_words: int | None = None,
) -> list[dict]:
    """Inspect a structured shot dict or raw compiled prompt for cross-field contradictions."""
    if not isinstance(shot, dict) or not any(shot.values()):
        return []

    raw_prompt = _field(shot, "raw_prompt")
    start = _field(shot, "start", "first_frame", "ref_lock", "world")
    light = _field(shot, "light", "setting")
    camera = _field(shot, "camera")
    action = _field(shot, "action", "timeline")
    ambient = _field(shot, "ambient")
    guard = _field(shot, "guard", "never")
    audio = _field(shot, "audio", "sound")
    voice = _field(shot, "voice")

    combined = raw_prompt or " ".join(
        part for part in (start, light, camera, action, ambient, guard, audio, voice) if part
    )
    if not combined.strip():
        return []

    findings: list[dict] = []

    # 1. Light conflict
    findings.extend(_check_light_conflict(light, f"{start} {light}" if (start or light) else combined))

    # 2. Camera vs Action conflict
    cam_src = strip_negated_clauses(camera)
    act_src = strip_negated_clauses(action)
    cam_static = bool(CAM_STATIC_RE.search(cam_src))
    cam_move = bool(CAM_MOVE_RE.search(cam_src))
    act_static = bool(CAM_STATIC_RE.search(act_src))
    act_move = bool(CAM_MOVE_RE.search(act_src))
    act_exit = bool(ACTION_EXIT_RE.search(act_src))
    if not camera and raw_prompt:
        raw_clean = strip_negated_clauses(raw_prompt)
        if CAM_STATIC_RE.search(raw_clean) and (CAM_MOVE_RE.search(raw_clean) or ACTION_EXIT_RE.search(raw_clean)):
            findings.append({
                "code": "camera_action_conflict",
                "severity": "error",
                "message": "Static/locked-off camera conflicts with camera movement or subject exiting frame.",
            })
    elif (cam_static and not cam_move and (act_move or act_exit)) or (cam_move and not cam_static and act_static) or (act_static and act_exit):
        findings.append({
            "code": "camera_action_conflict",
            "severity": "error",
            "message": "Camera instruction conflicts with Action movement or frame-exit displacement.",
        })

    # 3. Indoor vs outdoor vocabulary bleed (do NOT strip negations: "no villages or huts" causes pink-elephant bleed)
    indoor_flag = shot.get("indoor")
    indoor_probe = f"{start} {light}" if (start or light) else combined
    if indoor_flag is None:
        indoor_flag = bool(INDOOR_SCENE_RE.search(indoor_probe)) and not bool(WINDOW_OR_OUTSIDE_RE.search(indoor_probe))
    if indoor_flag:
        bleed_scope = f"{start} {ambient} {guard}" if (start or ambient or guard) else combined
        if OUTDOOR_BLEED_RE.search(bleed_scope) or HUT_BLEED_RE.search(bleed_scope) or (
            guard and re.search(r"\bhuts?\b", guard, re.I)
        ):
            findings.append({
                "code": "indoor_outdoor_bleed",
                "severity": "error",
                "message": "Indoor shot contains outdoor landscape/village/hut anchor or negative-list terms.",
            })

    # 4. No-speech vocal trigger pollution
    no_speech = shot.get("no_speech")
    if no_speech is None:
        no_speech = mode != "r2v-dialogue" or bool(SPEECH_DENY_RE.search(f"{audio} {voice} {combined}"))
    if no_speech:
        vocal_scope = " ".join(p for p in (start, action, audio, voice) if p) or combined
        vocal_clean = strip_negated_clauses(vocal_scope)
        m = VOCAL_TRIGGER_RE.search(vocal_clean)
        if m:
            findings.append({
                "code": "no_speech_vocal_trigger",
                "severity": "error",
                "message": f"No-speech shot contains vocal trigger '{m.group(0)}' outside negated clauses.",
            })

    # 5. Blank carrier vs read/write action conflict
    if BLANK_CARRIER_LOCK_RE.search(f"{guard} {combined}"):
        rw_scope = strip_negated_clauses(" ".join(p for p in (start, action) if p) or combined)
        m = READ_WRITE_ACTION_RE.search(rw_scope)
        if m:
            findings.append({
                "code": "blank_carrier_read_conflict",
                "severity": "error",
                "message": f"Action '{m.group(0)}' conflicts with blank/no-readable-writing lock.",
            })

    # 6. Menu-style audio options ("choose from:")
    audio_scope = f"{audio} {voice} {raw_prompt}".strip()
    if MENU_AUDIO_RE.search(audio_scope):
        findings.append({
            "code": "menu_choice_audio",
            "severity": "error",
            "message": "Audio prompt uses menu-choice wording ('choose from:') instead of concrete ambience/foley.",
        })

    # 7. CUTS TO leakage into compiled shot prompt
    if mode != "legacy" and CUTS_TO_RE.search(combined):
        findings.append({
            "code": "cuts_to_leak",
            "severity": "error",
            "message": "Compiled shot prompt contains CUTS TO / next-shot preview that induces early scene cuts.",
        })

    # 8. Word budget warning
    limit = max_words if max_words is not None else DEFAULT_MAX_WORDS.get(mode, 120)
    words = _word_count(raw_prompt or combined)
    if words > limit:
        findings.append({
            "code": "word_budget_exceeded",
            "severity": "warning",
            "message": f"Prompt has {words} words, exceeding {mode} budget of {limit} words (attention dilution risk).",
        })

    return findings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Lint AI video shot prompts for cross-field conflicts.")
    ap.add_argument("input", type=Path, help="JSON file (single shot dict or list of shot dicts) or plain .txt prompt")
    ap.add_argument("--mode", default="i2v-action", choices=sorted(DEFAULT_MAX_WORDS))
    ap.add_argument("--max-words", type=int, default=None)
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args(argv)

    raw = args.input.read_text(encoding="utf-8")
    if args.input.suffix.lower() == ".json":
        loaded = json.loads(raw)
        items = loaded if isinstance(loaded, list) else [loaded]
    else:
        items = [{"id": args.input.stem, "raw_prompt": raw}]

    results = []
    has_error = False
    for idx, item in enumerate(items):
        sid = item.get("id") or f"shot-{idx + 1}"
        issues = lint_shot_prompt(item, mode=args.mode, max_words=args.max_words)
        if any(x["severity"] == "error" for x in issues):
            has_error = True
        results.append({"id": sid, "issues": issues})

    if args.as_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for row in results:
            for issue in row["issues"]:
                print(f"[{issue['severity'].upper()}] {row['id']} ({issue['code']}): {issue['message']}")
    return 1 if has_error else 0


if __name__ == "__main__":
    sys.exit(main())
