import re
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import lint_video_prompt as lvp


def clean_still():
    return {
        "id": "1083-2",
        "start": "Exact start image as frame 1; 1 figure right of center (Zhang Jue, late 40s, gray-streaked beard, cloth headband, brown robe, wooden staff).",
        "camera": "Locked-off tripod low-angle medium shot; zero pan, tilt, zoom or dolly; frame edges identical 0-10s.",
        "action": "0-10s: figure holds exact start pose with subtle breathing, mouth closed.",
        "ambient": "Torch flames flickering; robe hem stirring in evening wind.",
        "guard": "Single continuous shot; no readable writing; held staff stays in hand.",
        "audio": "Soft evening wind and faint cloth rustle only; no music, no speech, no human vocalizations.",
        "indoor": False,
    }


def test_clean_prompts_pass_with_zero_issues():
    assert lvp.lint_shot_prompt(clean_still(), mode="i2v-still") == []
    t2v = {
        "id": "EB07-M07",
        "raw_prompt": (
            "Landscape 16:9. Photorealistic historical cinema. Calm sunlit modern library window seat in late afternoon golden light. "
            "Medium close-up: a junior-high student turns a page of a clean cloth-bound book, looks up thoughtfully through the tall window "
            "at wide blue sky and clouds, and writes a confident note in a plain cream notebook with NO readable text. "
            "Single continuous shot. Natural crisp page turn only; NO MUSIC, NO SPEECH, NO NARRATION."
        ),
    }
    assert lvp.lint_shot_prompt(t2v, mode="t2v") == []
    assert lvp.lint_shot_prompt({}, mode="i2v-action") == []


def test_catches_1084_light_and_indoor_bleed_and_vocal_trigger():
    shot = {
        "id": "1084-1",
        "start": "In 184 AD, dry gray winter fields near a county town, dirt roads, wooden carts. Inside a dim lamplit room, men sit close around a table, all speaking in low voices.",
        "light": "Night, dim lamplight indoors; bright daylight in government hall.",
        "camera": "Locked-off medium shot, no push-in.",
        "action": "Seated men keep their postures.",
        "guard": "No readable writing; no new people, villages or huts appear.",
        "audio": "choose from: low room tone, flame flicker.",
        "voice": "No speech; at most a gasp or sigh.",
    }
    codes = {x["code"] for x in lvp.lint_shot_prompt(shot, mode="i2v-still")}
    assert {"light_conflict", "indoor_outdoor_bleed", "no_speech_vocal_trigger", "menu_choice_audio"} <= codes


def test_catches_1085_static_camera_vs_gallop_away_and_blank_read_and_cuts_to():
    shot = {
        "id": "1085-1",
        "camera": "Locked-off wide shot. Camera remains still. No push, no zoom.",
        "action": "Static wide shot, distant riders gallop away into the distance while an officer reads from a scroll.",
        "guard": "No readable writing anywhere; CUTS TO: next shot starts at the city gate.",
        "audio": "Hoofbeats and distant orders only; no music, no speech.",
    }
    issues = lvp.lint_shot_prompt(shot, mode="i2v-action")
    codes = {x["code"] for x in issues}
    assert {"camera_action_conflict", "blank_carrier_read_conflict", "no_speech_vocal_trigger", "cuts_to_leak"} <= codes


def test_word_budget_warning_and_negation_stripping():
    s = clean_still()
    s["raw_prompt"] = " ".join(["word"] * 105)
    issues = lvp.lint_shot_prompt(s, mode="i2v-still")
    assert [(x["code"], x["severity"]) for x in issues] == [("word_budget_exceeded", "warning")]
    # Cloth map pointing is allowed even with blank lock
    s2 = clean_still()
    s2["action"] = "0-4s: one hand points at a marked spot on a plain cloth map; 4-10s: holds still."
    assert lvp.lint_shot_prompt(s2, mode="i2v-action") == []


def test_mutations_stop_rejecting_defects():
    never = re.compile(r"(?!x)x")
    bad_light = {"light": "Night, dim lamplight indoors; bright daylight in government hall."}
    with mock.patch.object(lvp, "DAY_LIGHT_RE", never):
        assert "light_conflict" not in {x["code"] for x in lvp.lint_shot_prompt(bad_light)}
    bad_cam = {"camera": "Locked-off tripod.", "action": "Slow push-in toward the gate."}
    with mock.patch.object(lvp, "CAM_MOVE_RE", never):
        assert "camera_action_conflict" not in {x["code"] for x in lvp.lint_shot_prompt(bad_cam)}
    bad_vocal = {"action": "Crowd cheers.", "audio": "Wind only; no speech."}
    with mock.patch.object(lvp, "VOCAL_TRIGGER_RE", never):
        assert "no_speech_vocal_trigger" not in {x["code"] for x in lvp.lint_shot_prompt(bad_vocal)}
