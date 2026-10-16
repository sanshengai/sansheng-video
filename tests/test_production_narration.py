import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import production_narration as narration


class NarrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.audio = self.root / "speech.wav"
        with wave.open(str(self.audio), "wb") as stream:
            stream.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
            stream.writeframes(b"\0\0" * 16000)
        self.record = self.root / "record.json"
        self.original = {"audio": {"path": self.audio.name, "sha256": narration.digest(self.audio),
            "duration": 2, "text": "先观察。再比较。", "chunks": [
                {"text": "先观察。", "at": 0, "duration": .8},
                {"text": "再比较。", "at": 1, "duration": 1}]}}
        self.record.write_text(json.dumps(self.original))
        self.evidence = self.root / "evidence.json"

    def store(self, value):
        self.evidence.write_text(json.dumps(value))

    def test_actual_audio_duration_and_record_anchors_round_trip(self):
        result = narration.import_evidence(self.record, self.audio)
        self.assertEqual(2, result["duration"])
        self.assertEqual(self.original["audio"]["chunks"], result["blocks"])
        self.assertEqual(narration.digest(self.record), result["source_record_sha256"])
        self.store(result)
        self.assertEqual(result, narration.verify_evidence(self.evidence))

    def test_audio_change_is_rejected(self):
        self.store(narration.import_evidence(self.record, self.audio))
        self.audio.write_bytes(self.audio.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "audio SHA256"):
            narration.verify_evidence(self.evidence)

    def test_tampered_text_and_consistent_but_unoriginal_text_are_rejected(self):
        original = narration.import_evidence(self.record, self.audio)
        for consistent in (False, True):
            changed = copy.deepcopy(original)
            changed["text"] = "换文字。再比较。"
            if consistent:
                changed["blocks"][0]["text"] = "换文字。"
            self.store(changed)
            with self.subTest(consistent=consistent), self.assertRaisesRegex(ValueError, "text|differs"):
                narration.verify_evidence(self.evidence)

    def test_outside_overlap_missing_and_empty_blocks_rejected(self):
        original = narration.import_evidence(self.record, self.audio)
        changes = [lambda x: x["blocks"][0].update(at=-1),
                   lambda x: x["blocks"][1].update(duration=2),
                   lambda x: x["blocks"][1].update(at=.5),
                   lambda x: x.update(blocks=[]),
                   lambda x: x["blocks"].pop(),
                   lambda x: x["blocks"][0].update(text="")]
        for change in changes:
            value = copy.deepcopy(original)
            change(value)
            self.store(value)
            with self.subTest(value=value), self.assertRaises(ValueError):
                narration.verify_evidence(self.evidence)

    def test_changed_source_record_and_duration_mismatch_are_rejected(self):
        self.store(narration.import_evidence(self.record, self.audio))
        self.record.write_text(self.record.read_text() + " ")
        with self.assertRaisesRegex(ValueError, "differs"):
            narration.verify_evidence(self.evidence)
        self.original["audio"]["duration"] = 3
        self.record.write_text(json.dumps(self.original))
        with self.assertRaisesRegex(ValueError, "duration differs"):
            narration.import_evidence(self.record, self.audio)

    def test_invalid_anchors_in_original_record_are_rejected(self):
        changes = [lambda x: x["chunks"][0].update(at=-1),
                   lambda x: x["chunks"][1].update(duration=2),
                   lambda x: x["chunks"][1].update(at=.5),
                   lambda x: x.update(chunks=[]),
                   lambda x: x.update(chunks=None),
                   lambda x: x["chunks"].pop(),
                   lambda x: x["chunks"][0].update(text="")]
        for change in changes:
            value = copy.deepcopy(self.original)
            change(value["audio"])
            self.record.write_text(json.dumps(value))
            with self.subTest(value=value), self.assertRaises(ValueError):
                narration.import_evidence(self.record, self.audio)

    def test_source_changes_during_probe_are_rejected(self):
        original = narration.probe_duration
        def changed(path):
            result = original(path)
            self.record.write_text(self.record.read_text() + " ")
            return result
        with mock.patch.object(narration, "probe_duration", side_effect=changed):
            with self.assertRaisesRegex(ValueError, "changed during"):
                narration.import_evidence(self.record, self.audio)

    def test_evidence_changes_during_probe_are_rejected(self):
        self.store(narration.import_evidence(self.record, self.audio))
        original = narration.probe_duration

        def changed(path):
            result = original(path)
            self.evidence.write_text(self.evidence.read_text() + " ")
            return result

        with mock.patch.object(narration, "probe_duration", side_effect=changed):
            with self.assertRaisesRegex(ValueError, "evidence changed during"):
                narration.verify_evidence(self.evidence)

    def test_verified_inputs_reject_change_after_evidence_validation(self):
        self.store(narration.import_evidence(self.record, self.audio))
        original = narration.verify_evidence

        def changed(path):
            result = original(path)
            self.audio.write_bytes(self.audio.read_bytes() + b"changed")
            return result

        with mock.patch.object(narration, "verify_evidence", side_effect=changed):
            with self.assertRaisesRegex(ValueError, "changed after verification"):
                narration.verified_inputs(self.evidence)


if __name__ == "__main__":
    unittest.main()
