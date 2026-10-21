import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import production_timeline
import package_delivery
import brand_assets


class PromotionTests(unittest.TestCase):
    def fixture(self, root):
        evidence = root / "source.txt"
        evidence.write_text("Captured product result, revision one")
        brief = {"kind": "promotion-brief/1", "mode": "showcase", "audience": "Creators",
                 "promise": "Useful visual work", "title": "Make your ideas visible", "destination": "Product page",
                 "evidence": [{"id": "work", "file": "source.txt", "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
                               "version": "one", "acquired_at": "2026-01-01T00:00:00Z"}],
                 "claims": [{"id": "useful", "benefit": "Usable illustration", "evidence_ids": ["work"]}]}
        (root / "brief.json").write_text(json.dumps(brief))
        timeline = {"fps": 30, "duration": 4, "canvas": [1280, 720], "requires_audio": False,
                    "shots": [{"id": "one", "start": 0, "end": 4}], "promotion": "brief.json",
                    "events": [{"id": "reveal", "scene_id": "one", "start": 0, "end": 4,
                                "visual": {"type": "work"}, "timing_basis": "authored", "claim_ids": ["useful"]}]}
        source = root / "timeline.json"
        source.write_text(json.dumps(timeline))
        return source, timeline, brief, evidence

    def test_actual_export_binds_evidence_and_rejects_mutations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, timeline, brief, evidence = self.fixture(root)
            derived = root / "derived"
            production_timeline.export(source, derived)
            self.assertIn('"claim_ids"', (derived / "events.js").read_text())
            self.assertIn(str(evidence), (derived / "promotion-plan.json").read_text())
            production_timeline.check(derived / "production-build.json")
            evidence.write_text("Changed product revision")
            with self.assertRaisesRegex(ValueError, "stale"):
                production_timeline.check(derived / "production-build.json")
            with self.assertRaisesRegex(ValueError, "fingerprint"):
                production_timeline.export(source, derived, refresh=True)
            evidence.unlink()
            with self.assertRaisesRegex(ValueError, "missing or empty"):
                production_timeline.export(source, derived, refresh=True)

    def test_unknown_missing_and_unconsumed_claims(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, timeline, brief, _ = self.fixture(root)
            for change in (lambda d: d["events"][0].update(claim_ids=["unknown"]),
                           lambda d: d["events"][0].update(claim_ids=[]),
                           lambda d: d.pop("promotion")):
                altered = copy.deepcopy(timeline)
                change(altered)
                source.write_text(json.dumps(altered))
                with self.assertRaises(ValueError):
                    production_timeline.export(source, root / "derived")
            source.write_text(json.dumps(timeline))
            for change in (lambda b: b.update(evidence=[]), lambda b: b.update(claims=[]),
                           lambda b: b["claims"][0].update(evidence_ids=["unknown"]),
                           lambda b: b["evidence"][0].update(acquired_at="2026-01-01")):
                altered = copy.deepcopy(brief)
                change(altered)
                (root / "brief.json").write_text(json.dumps(altered))
                with self.assertRaises(ValueError):
                    production_timeline.export(source, root / "derived")


class BrandTests(unittest.TestCase):
    def test_visible_bounds_and_legacy_and_explicit_roles(self):
        from PIL import Image, ImageDraw
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            logo = Image.new("RGBA", (200, 100))
            ImageDraw.Draw(logo).rectangle((50, 25, 149, 74), fill="white")
            logo.save(root / "logo.png")
            config = root / "profile.json"
            config.write_text(json.dumps({"brand": {"logo_on_dark": "logo.png"}}))
            self.assertEqual("unspecified_legacy", brand_assets.resolve(config)["type"])
            result = brand_assets.preview(config, root / "preview.png", (1000, 1000), .2)
            self.assertEqual([50, 25, 150, 75], result["alpha_bounds"])
            self.assertEqual(200, result["visible_box"][2] - result["visible_box"][0])
            config.write_text(json.dumps({"brand": {"variants": {"full": {"file": "logo.png", "type": "full",
                                                        "background": "dark", "roles": ["ending"]}}}}))
            with self.assertRaisesRegex(ValueError, "no configured"):
                brand_assets.resolve(config)
            self.assertEqual("full", brand_assets.resolve(config, role="ending")["type"])
            (root / "logo.png").unlink()
            with self.assertRaisesRegex(ValueError, "missing"):
                brand_assets.resolve(config, role="ending")


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
class DeliveryTests(unittest.TestCase):
    def test_real_video_copy_preview_repeat_and_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "source.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=160x90:r=24:d=0.5",
                            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)], check=True, capture_output=True)
            spec = root / "delivery-spec.json"
            data = {"video": "source.mp4", "filename": "Product-portrait-v2.mp4", "title": "Product",
                    "summary": "Works and controls", "suggested_title": "Make ideas visible", "project": str(root),
                    "review_status": "candidate"}
            spec.write_text(json.dumps(data))
            dest = root / "handoff"
            result = package_delivery.package(spec, dest)
            self.assertEqual(package_delivery.digest(video), package_delivery.digest(result["video"]))
            self.assertIn(data["filename"], (dest / "preview.html").read_text())
            self.assertFalse(result["uploaded"])
            package_delivery.package(spec, dest)
            (dest / data["filename"]).write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "different content"):
                package_delivery.package(spec, dest)
            self.assertEqual(b"changed", (dest / data["filename"]).read_bytes())
            video.unlink()
            with self.assertRaises(ValueError):
                package_delivery.package(spec, root / "another")


if __name__ == "__main__":
    unittest.main()
