"""Consumer tests for explicit staged audio; fixtures live outside the Skill tree."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import wave

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "generate_sfx_tags.py"
spec = importlib.util.spec_from_file_location("sfx_staged", MODULE)
sfx = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sfx)


class StagedCues(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sfx-cues-")
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.index = self.project / "hf" / "index.html"
        self.audio = self.project / "hf" / "assets" / "picked" / "source.wav"
        self.audio.parent.mkdir(parents=True)
        with wave.open(str(self.audio), "wb") as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(8000)
            stream.writeframes(b"\0\0" * 4000)
        self.index.write_text('<html><body>\n<div id="root" data-composition-id="main" data-duration="10">\n  <div class="clip" data-composition-src="compositions/child.html" data-start="3" data-duration="3"></div>\n  <audio id="manual-vo" src="voice.wav" data-track-index="0"></audio>\n  </div>\n<script>const sentinel = 10;</script>\n</body></html>\n')
        self.item = {"id": "audio-selected", "revision": "revision-1", "scene_id": "scene-2", "sha256": hashlib.sha256(self.audio.read_bytes()).hexdigest(), "project_path": "hf/assets/picked/source.wav", "cues": [{"id": "subcomp-hit", "time": 3.25, "duration": 0.25, "volume": 0.3}]}
        self.manifest = self.project / "assets.lock.json"
        self.save()

    def save(self):
        self.manifest.write_text(json.dumps({"items": [self.item]}))

    def invoke(self, *args):
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()) as err:
            code = sfx.main([str(self.index), *args])
        return code, out.getvalue(), err.getvalue()

    def assert_rejected_without_mutation(self, *args):
        before = self.index.read_bytes()
        code, _, err = self.invoke("--apply", *args)
        self.assertEqual(code, 1, err)
        self.assertEqual(self.index.read_bytes(), before)
        self.assertFalse(list(self.index.parent.glob("*.bak")))
        return err

    def test_unsupported_cue_timing_is_never_silently_ignored(self):
        original = dict(self.item["cues"][0])
        fields = {"media_start": 0.1, "source_start": 0.1, "source_in": 0.1,
                  "playback_rate": 2, "source_anchor": 0.2,
                  "action_time": 3.5, "duraton": 0.25}
        for external in (False, True):
            for field, value in fields.items():
                with self.subTest(external=external, field=field):
                    cue = dict(original, **{field: value})
                    self.item["cues"] = [cue]
                    self.save()
                    args = []
                    if external:
                        path = self.project / "explicit-cues.json"
                        path.write_text(json.dumps([dict(cue, asset_id=self.item["id"])]))
                        args = ["--cues", str(path)]
                    err = self.assert_rejected_without_mutation(*args)
                    self.assertIn("不支持的 cue 字段", err)
                    self.assertIn(field, err)

    def test_readonly_then_apply_subcomp_absolute_cue_and_idempotency(self):
        files = set(self.project.rglob("*"))
        before = self.index.read_bytes()
        code, stdout, err = self.invoke()
        self.assertEqual(code, 0, err)
        self.assertEqual(self.index.read_bytes(), before)
        self.assertEqual(set(self.project.rglob("*")), files)
        event = json.loads(stdout)["events"][0]
        self.assertEqual(event["time"], 3.25)
        self.assertEqual(event["asset_id"], "audio-selected")
        self.assertEqual(event["src"], "assets/picked/source.wav")
        self.assertEqual(self.invoke("--apply")[0], 0)
        rendered = self.index.read_bytes()
        self.assertIn(b'id="manual-vo"', rendered)
        self.assertIn(b'<script>const sentinel', rendered)
        self.assertEqual(rendered.count(b'id="subcomp-hit"'), 1)
        self.assertLess(rendered.index(b'id="subcomp-hit"'), rendered.index(b'  </div>\n<script>'))
        self.assertEqual(self.invoke("--apply")[0], 0)
        self.assertEqual(self.index.read_bytes(), rendered)
        self.assertEqual(len(list(self.index.parent.glob("*.bak"))), 1)

    def test_crlf_backup_preserves_original_bytes(self):
        original = self.index.read_text().replace('\n', '\r\n').encode()
        self.index.write_bytes(original)
        code, _, err = self.invoke("--apply")
        self.assertEqual(code, 0, err)
        self.assertEqual(next(self.index.parent.glob("*.bak")).read_bytes(), original)
        applied = self.index.read_bytes()
        self.assertEqual(self.invoke("--apply")[0], 0)
        self.assertEqual(self.index.read_bytes(), applied)

    def test_missing_file_rejected(self):
        self.audio.unlink()
        self.assertIn("缺文件", self.assert_rejected_without_mutation())

    def test_changed_hash_rejected(self):
        self.audio.write_bytes(self.audio.read_bytes() + b"changed")
        self.assertIn("哈希", self.assert_rejected_without_mutation())

    def test_symlink_escape_rejected(self):
        outside = self.project / "outside.wav"
        outside.write_bytes(self.audio.read_bytes())
        self.audio.unlink()
        self.audio.symlink_to(outside)
        self.assertIn("symlink", self.assert_rejected_without_mutation())

    def test_parent_path_rejected(self):
        self.item["project_path"] = "../outside.wav"
        self.save()
        self.assertIn("越界", self.assert_rejected_without_mutation())

    def test_duplicate_cue_rejected(self):
        self.item["cues"] *= 2
        self.save()
        self.assertIn("重复", self.assert_rejected_without_mutation())

    def test_invalid_empty_and_outside_cues_rejected(self):
        for cues in ([], [{"time": -1}], [{"time": float("nan")}], [{"time": 9.9, "duration": .5}], [{"time": True}], [{"time": 1, "duration": 2}]):
            with self.subTest(cues=cues):
                self.item["cues"] = cues
                self.save()
                self.assert_rejected_without_mutation()

    def test_explicit_cues_resolve_lock_and_reject_unknown(self):
        self.item.pop("cues")
        self.save()
        cues = self.project / "chosen-cues.json"
        cues.write_text(json.dumps([{"asset_id": "audio-selected", "scene_id": "scene-2", "time": 1.5}]))
        code, out, err = self.invoke("--cues", str(cues))
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["events"][0]["time"], 1.5)
        cues.write_text(json.dumps([{"asset_id": "not-staged", "time": 1}]))
        self.assertIn("唯一匹配", self.assert_rejected_without_mutation("--cues", str(cues)))

    def test_track_collision_with_manual_audio_rejected(self):
        self.item["cues"][0]["track"] = 0
        self.save()
        self.assertIn("手工轨道", self.assert_rejected_without_mutation())

    def test_missing_root_rejected(self):
        self.index.write_text('<html><body>plain html</body></html>')
        self.assertIn("根", self.assert_rejected_without_mutation())

    def test_empty_lock_and_broken_marks_rejected_without_writes(self):
        self.manifest.write_text('{"items": []}')
        self.assertIn("非空", self.assert_rejected_without_mutation())
        self.save()
        valid = self.index.read_text()
        for marks in (sfx.BEGIN, sfx.END + sfx.BEGIN):
            self.index.write_text(valid.replace('<script>', marks + '<script>'))
            self.assertIn("标记", self.assert_rejected_without_mutation())

    def test_legacy_auto_tag_on_minified_line_preserves_following_html(self):
        self.index.write_text(self.index.read_text().replace('  </div>\n<script>', '<audio data-sfx-auto="1" src="old.wav"></audio></div>\n<script>'))
        code, _, err = self.invoke("--apply")
        self.assertEqual(code, 0, err)
        rendered = self.index.read_text()
        self.assertNotIn('old.wav', rendered)
        self.assertIn('</div>\n<script>const sentinel', rendered)
        self.assertEqual(self.invoke("--apply")[0], 0)
        self.assertEqual(self.index.read_text(), rendered)

    def test_overlapping_track_rejected(self):
        self.item["cues"] = [{"id": "cue-a", "time": 1, "track": 2}, {"id": "cue-b", "time": 1.1, "track": 2}]
        self.save()
        self.assertIn("重叠", self.assert_rejected_without_mutation())

    def test_manifest_search_does_not_walk_arbitrary_ancestors(self):
        deeper = self.project / "hf" / "deep" / "index.html"
        deeper.parent.mkdir()
        deeper.write_text(self.index.read_text())
        with self.assertRaisesRegex(ValueError, "缺 assets.lock"):
            sfx.find_manifest(deeper)
        self.assertEqual(sfx.find_manifest(deeper, self.manifest), self.manifest.resolve())


if __name__ == "__main__":
    unittest.main()
