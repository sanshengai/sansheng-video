import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from runtime_support import managed_command
spec = importlib.util.spec_from_file_location("video_setup", ROOT / "setup.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)

class PortableSetupTests(unittest.TestCase):
    def test_core_needs_no_private_profile_or_scheduler(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(setup, "ROOT", Path(tmp)), patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(setup.profile())
            self.assertEqual(["ffmpeg", "argument with spaces"], managed_command(["ffmpeg", "argument with spaces"]))

    def test_scheduler_prefix_preserves_argv_without_shell_evaluation(self):
        with patch.dict(os.environ, {"SANSHENG_VIDEO_COMMAND_PREFIX": '["queue", "--"]'}):
            self.assertEqual(["queue", "--", "ffmpeg", "$(not-a-command)"], managed_command(["ffmpeg", "$(not-a-command)"]))
        for bad in ("[]", '"queue"', '[3]', '[""]', "invalid"):
            with self.subTest(bad=bad), patch.dict(os.environ, {"SANSHENG_VIDEO_COMMAND_PREFIX": bad}), self.assertRaises(ValueError):
                managed_command(["ffmpeg"])

    def test_profile_is_explicit_and_bad_configuration_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "profile.json"
            path.write_text(json.dumps({"brand": {"name": "Neutral"}, "asset_roots": []}))
            self.assertEqual("Neutral", setup.profile(tmp)["configuration"]["brand"]["name"])
            for bad in ([], {"asset_roots": "not-an-array"}, {"brand": {"logo": "missing.png"}}):
                path.write_text(json.dumps(bad))
                with self.subTest(bad=bad), self.assertRaises((ValueError, OSError)):
                    setup.profile(tmp)
            path.unlink()
            with self.assertRaises(OSError):
                setup.profile(tmp)

    def test_retired_library_paths_are_not_exposed(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/"profile.json").write_text(json.dumps({"asset_roots":["/old/library"],"cold_storage_root":"/old/cloud","brand":{"name":"Current"}}))
            config = setup.profile(tmp)["configuration"]
            self.assertNotIn("asset_roots", config)
            self.assertNotIn("cold_storage_root", config)
            self.assertEqual(config["brand"]["name"], "Current")

    def test_disabled_browser_checks_are_not_reported(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(setup, "ROOT", Path(tmp)), patch.dict(os.environ, {}, clear=True), patch("shutil.which", return_value=None):
            result = setup.check()
        self.assertNotIn("browser_checks", result)
        self.assertNotIn("profile", result)
        self.assertEqual("needs_setup", result["status"])

    def test_user_created_profile_and_explicit_override(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(setup, "ROOT", Path(tmp)), patch.dict(os.environ, {}, clear=True):
            target = Path(tmp) / "profile"
            target.mkdir()
            (target / "profile.json").write_text('{"brand":{"name":"Local"}}')
            self.assertEqual("Local", setup.profile()["configuration"]["brand"]["name"])
            explicit = Path(tmp) / "override"
            explicit.mkdir()
            (explicit / "profile.json").write_text('{"brand":{"name":"Explicit"}}')
            with patch.dict(os.environ, {"SANSHENG_VIDEO_PROFILE_DIR": str(explicit)}):
                self.assertEqual("Explicit", setup.profile()["configuration"]["brand"]["name"])
            (target / "profile.json").write_text("")
            with self.assertRaises(ValueError):
                setup.profile()
