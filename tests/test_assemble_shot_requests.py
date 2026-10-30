import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import assemble_shot_requests as asr

LOCKS = {
    "style": {"default": "STYLE-A"},
    "characters": {"girl": "GIRL-LOCK"},
    "worlds": {"field": "FIELD-LOCK", "house": "HOUSE-LOCK"},
    "format": "FMT", "music": {"calm": "MUSIC-LOCK"},
    "voice": "no dialogue.", "mix": "MIX", "continuity": "KEEP",
}


def shot(**kw):
    base = {"id": "S01", "segment": "field", "first_frame": "ff", "action": ["a", "b", "c"],
            "camera": "cam", "ambient": "amb", "end_state": "end", "music_dynamic": "swell",
            "ambience": "wind", "foley": "none", "characters": ["girl"]}
    base.update(kw)
    return base


def table(tmp_path, shots, segments=None):
    p = tmp_path / "t.json"
    p.write_text(json.dumps({"locks": LOCKS, "segments": segments or {"field": {"world": "field", "music": "calm"}},
                             "shots": shots}))
    return p


def test_request_repeats_locks_verbatim_and_drops_none_foley(tmp_path):
    data = asr.load(table(tmp_path, [shot(), shot(id="S02", world="house")]))
    a, b = (asr.request(s, LOCKS, data["segments"]) for s in data["shots"])
    for text in (a, b):
        assert "STYLE: STYLE-A" in text and "CHARACTER GIRL: GIRL-LOCK" in text
        assert f"Music: {asr.MUSIC_NONE}" in text and "Foley" not in text
    assert "WORLD: FIELD-LOCK" in a and "WORLD: HOUSE-LOCK" in b
    assert "0-3s a / 3-7s b / 7-10s c" in a


def test_cast_lock_opens_request_and_closes_end_state(tmp_path):
    locks = dict(LOCKS, names={"girl": "HEHE"})
    text = asr.request(shot(extras=["one old woman"]), locks, {"field": {"world": "field"}})
    assert text.startswith("CAST: EXACTLY 2 CHARACTERS, NO DUPLICATES: HEHE, one old woman. No other people.")
    assert "END STATE (10s): end. Exactly 2 characters in frame: HEHE, one old woman." in text
    empty = asr.request(shot(characters=[]), LOCKS, {"field": {"world": "field"}})
    assert empty.startswith("CAST: NO PEOPLE IN FRAME") and "CONTINUITY" not in empty


def test_native_music_mode_uses_segment_lock_and_requires_dynamic(tmp_path):
    locks = dict(LOCKS, native_music=True)
    text = asr.request(shot(), locks, {"field": {"world": "field", "music": "calm"}})
    assert "Music: MUSIC-LOCK; swell" in text
    p = tmp_path / "n.json"
    p.write_text(json.dumps({"locks": locks, "segments": {"field": {"world": "field", "music": "calm"}},
                             "shots": [shot(music_dynamic="")]}))
    with pytest.raises(ValueError, match="music_dynamic"):
        asr.load(p)


def test_references_are_bound_to_roles_in_order(tmp_path):
    locks = dict(LOCKS, refs={"kf": {"file": "k.png", "use": "first frame"}, "girl": {"file": "g.png", "use": "identity only"}})
    text = asr.request(shot(refs=["kf", "girl"]), locks, {"field": {"world": "field"}})
    assert "REFERENCES: image 1 = kf (first frame); image 2 = girl (identity only)" in text


@pytest.mark.parametrize("bad, message", [
    ({"world": "missing"}, "场景锁"),
    ({"characters": ["ghost"]}, "角色锁"),
    ({"action": ["only one"]}, "action"),
    ({"camera": ""}, "缺字段"),
    ({"refs": ["nope"]}, "参考图"),
])
def test_load_rejects_broken_references(tmp_path, bad, message):
    with pytest.raises(ValueError, match=message):
        asr.load(table(tmp_path, [shot(**bad)]))


def test_load_rejects_duplicate_ids(tmp_path):
    with pytest.raises(ValueError, match="重复"):
        asr.load(table(tmp_path, [shot(), shot()]))


def test_batch_file_lists_references_once_in_order(tmp_path):
    locks = dict(LOCKS, refs={"girl": {"file": "g.png", "use": "identity"}, "field": {"file": "f.png", "use": "scene"}})
    p = tmp_path / "t.json"
    p.write_text(json.dumps({"locks": locks, "segments": {"field": {"world": "field", "music": "calm"}},
                             "shots": [shot(refs=["girl", "field"], batch="B1"), shot(id="S02", refs=["field"], batch="B1")]}))
    out = tmp_path / "out"
    sys.argv = ["x", str(p), "--out", str(out)]
    asr.main()
    text = (out / "B1.txt").read_text()
    assert text.startswith("REFERENCES (attach in this order):\n- girl: g.png | identity\n- field: f.png | scene\n")
    assert "===== S02 (?s) refs: field =====" in text
