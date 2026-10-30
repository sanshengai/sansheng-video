"""Revision proof: outside the scope nothing may change."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import compare_frames as cf

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None


def seek_dir(root, name, frames):
    """frames: {time: (r, g, b)} solid images plus optional pixel edits."""
    directory = Path(root) / name
    directory.mkdir()
    shots = []
    for i, (t, spec) in enumerate(sorted(frames.items())):
        color, pixel = spec if isinstance(spec, tuple) and len(spec) == 2 and isinstance(spec[0], tuple) else (spec, None)
        image = Image.new("RGB", (32, 18), color)
        if pixel:
            image.putpixel(pixel, (255, 0, 0))
        path = directory / f"forward-{i:03d}.png"
        image.save(path)
        shots.append({"mode": "forward", "time": t, "path": str(path)})
    (directory / "seek-report.json").write_text(json.dumps({"screenshots": shots}))
    return directory


@unittest.skipIf(Image is None, "Pillow not installed")
class FrameModeTests(unittest.TestCase):
    def run_main(self, old, new, scope):
        return cf.main([str(old), str(new), "--scope", scope, "--json"])

    def test_identical_outside_scope_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            frames = {1.0: (10, 10, 10), 4.0: (20, 20, 20), 8.0: (30, 30, 30)}
            old, new = seek_dir(temp, "old", frames), seek_dir(temp, "new", frames)
            self.assertEqual(0, self.run_main(old, new, "3-5"))

    def test_one_pixel_outside_scope_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            old = seek_dir(temp, "old", {1.0: (10, 10, 10), 4.0: (20, 20, 20)})
            new = seek_dir(temp, "new", {1.0: ((10, 10, 10), (5, 5)), 4.0: (20, 20, 20)})
            self.assertEqual(1, self.run_main(old, new, "3-5"))
            result = cf.compare_frames(old, new, cf.parse_scope("3-5"))
            self.assertEqual([1.0], [x["time"] for x in result["changed_outside"]])
            self.assertIn("1 个像素不同", result["changed_outside"][0]["detail"])

    def test_change_inside_scope_passes_and_is_listed(self):
        with tempfile.TemporaryDirectory() as temp:
            old = seek_dir(temp, "old", {1.0: (10, 10, 10), 4.0: (20, 20, 20)})
            new = seek_dir(temp, "new", {1.0: (10, 10, 10), 4.0: (200, 20, 20)})
            self.assertEqual(0, self.run_main(old, new, "3-5"))
            result = cf.compare_frames(old, new, cf.parse_scope("3-5"))
            self.assertEqual([4.0], [x["time"] for x in result["in_scope"]])

    def test_frame_missing_on_one_side_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            old = seek_dir(temp, "old", {1.0: (10, 10, 10), 8.0: (30, 30, 30)})
            new = seek_dir(temp, "new", {1.0: (10, 10, 10)})
            self.assertEqual(1, self.run_main(old, new, "3-5"))


class EdlModeTests(unittest.TestCase):
    EDL = {"scenes": [
        {"n": 1, "timeline_start": 0.0, "timeline_end": 2.0, "source": "a.mp4", "source_in": 0.5, "source_out": 2.5},
        {"n": 2, "timeline_start": 2.0, "timeline_end": 4.0, "source": "b.mp4", "source_in": 0.5, "source_out": 2.5},
        {"n": 3, "timeline_start": 4.0, "timeline_end": 6.0, "source": "c.mp4", "source_in": 0.5, "source_out": 2.5}]}

    def write(self, root, name, data):
        path = Path(root) / name
        path.write_text(json.dumps(data))
        return path

    def test_in_point_change_outside_scope_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            changed = copy.deepcopy(self.EDL)
            changed["scenes"][0]["source_in"] = 0.6
            changed["scenes"][0]["source_out"] = 2.6
            old, new = self.write(temp, "old.json", self.EDL), self.write(temp, "new.json", changed)
            self.assertEqual(1, cf.main([str(old), str(new), "--scope", "2.5-3.5", "--json"]))

    def test_change_inside_scope_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            changed = copy.deepcopy(self.EDL)
            changed["scenes"][1]["source"] = "b2.mp4"
            old, new = self.write(temp, "old.json", self.EDL), self.write(temp, "new.json", changed)
            self.assertEqual(0, cf.main([str(old), str(new), "--scope", "2.5-3.5", "--json"]))

    def test_bad_scope_or_input_is_unusable(self):
        with tempfile.TemporaryDirectory() as temp:
            old = self.write(temp, "old.json", self.EDL)
            self.assertEqual(2, cf.main([str(old), str(old), "--scope", "5-3"]))
            self.assertEqual(2, cf.main([str(old), str(old), "--scope", "abc"]))
            bad = self.write(temp, "bad.json", {"scenes": [{"n": 1}]})
            self.assertEqual(2, cf.main([str(old), str(bad), "--scope", "1-2"]))


if __name__ == "__main__":
    unittest.main()
