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


def test_nobody_speaks_is_negated_while_positive_vocal_still_triggers():
    clean_silent = {
        "action": "Action: Real-time continuous take. Maya closes the cardboard tube quietly.",
        "voice": "Speech: Nobody speaks; all lips stay closed.",
        "audio": "Audio: Quiet sea breeze and cardboard rustle only. No music, no speech, no human vocalizations.",
        "no_speech": True,
    }
    assert lvp.lint_shot_prompt(clean_silent, mode="i2v-action") == []
    bad_silent = dict(
        clean_silent,
        action="Action: Real-time continuous take. Everyone in the circle talks and smiles at once.",
    )
    assert "no_speech_vocal_trigger" in {x["code"] for x in lvp.lint_shot_prompt(bad_silent, mode="i2v-action")}


def test_cinematography_lint_warnings_and_mutations():
    # 1. Vague buzzwords without concrete light/optics warn in keyframe & t2v modes
    vague_kf = {
        "id": "KF01",
        "raw_prompt": "Photorealistic cinematic film still, natural light, a merchant standing by a wooden gate.",
    }
    assert "vague_style_without_optics" in {x["code"] for x in lvp.lint_keyframe_prompt(vague_kf)}

    concrete_kf = {
        "id": "KF02",
        "raw_prompt": (
            "Photorealistic cinematic film still, warm late-afternoon side sunlight through timber eaves, "
            "subtle 35mm film grain, light airborne dust, 35mm medium shot of a merchant by a wooden gate."
        ),
    }
    assert lvp.lint_keyframe_prompt(concrete_kf) == []

    # 2. Close-up paired with ultra-wide lens warns
    bad_lens = {"id": "KF03", "raw_prompt": "Close-up portrait of a general, shot on 14mm ultra-wide lens, side light."}
    assert "closeup_ultrawide_conflict" in {x["code"] for x in lvp.lint_keyframe_prompt(bad_lens)}

    # 3. Dynamic camera move paired with static composition lock warns
    bad_move_lock = {
        "id": "V01",
        "start": "Exact start image as frame 1, keep exact composition and lighting.",
        "camera": "Single slow dolly-in from frame 1 through second 10.",
        "action": "0-7s: officer raises one hand steadily.",
        "audio": "Soft wind only; no music, no speech, no human vocalizations.",
    }
    assert "static_composition_vs_camera_move" in {x["code"] for x in lvp.lint_shot_prompt(bad_move_lock, mode="i2v-continuous")}

    clean_continuous = dict(
        bad_move_lock,
        start="Exact start image as frame 1, keep scene, subjects and lighting consistent.",
    )
    assert lvp.lint_shot_prompt(clean_continuous, mode="i2v-continuous") == []

    # Mutation tests prove each new detector actually rejects defects
    never = re.compile(r"(?!x)x")
    with mock.patch.object(lvp, "VAGUE_STYLE_BUZZ_RE", never):
        assert "vague_style_without_optics" not in {x["code"] for x in lvp.lint_keyframe_prompt(vague_kf)}
    with mock.patch.object(lvp, "ULTRAWIDE_LENS_RE", never):
        assert "closeup_ultrawide_conflict" not in {x["code"] for x in lvp.lint_keyframe_prompt(bad_lens)}
    with mock.patch.object(lvp, "STATIC_COMPOSITION_LOCK_RE", never):
        assert "static_composition_vs_camera_move" not in {
            x["code"] for x in lvp.lint_shot_prompt(bad_move_lock, mode="i2v-continuous")
        }

