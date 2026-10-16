"""Independent safety checks for the geometry path input contract."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from geometry_strokes import SLOT, inject_strokes, normalize_strokes


class GeometryStrokesTest(unittest.TestCase):
    def test_normalizes_and_injects_triangle_without_markup_escape(self):
        strokes = [
            {"d": "M 230 430 L 770 430 L 540 105 Z"},
            {"d": "M 540 105 L 540 430", "accent": True, "width": 5},
            {"d": "M 540 410 L 560 410 L 560 430"},
        ]
        normalized = normalize_strokes(strokes)
        self.assertEqual(normalized[0]["d"], "M 230 430 L 770 430 L 540 105 Z")
        self.assertEqual(normalized[1]["width"], 5.0)
        html = inject_strokes("before" + SLOT + "after", strokes)
        self.assertIn('data-ink="accent" stroke-width="5"', html)
        self.assertEqual(html.count("<path"), 3)
        self.assertEqual(html.count('data-slot="strokes"'), 1)

    def test_rejects_markup_script_and_unsupported_commands(self):
        bad_paths = [
            'M 0 0 L 2 2" onload="alert(1)',
            "M 0 0 <script>alert(1)</script>",
            "M 0 0 A 3 3 0 0 1 5 5",
            "M 0 0 L 2 2;alert(1)",
            "M 0 0 L 1e999 2",
            "M 0 0 l 2 2",
            "M 0 0 L 1600 400",
            "M 0 0 L 800 760",
            "M 0 0 H 1001",
            "M 0 0 V 561",
        ]
        for path in bad_paths:
            with self.subTest(path=path), self.assertRaises(ValueError):
                normalize_strokes([{"d": path}])

    def test_rejects_empty_oversize_and_malformed_paths(self):
        bad = [
            [], [{"d": "M 0 0"}], [{"d": "L 1 2"}],
            [{"d": "M 0 0 L 1"}], [{"d": "M 0 0 L 2 2", "width": float("nan")}],
            [{"d": "M 0 0 L 2 2", "accent": "yes"}],
            [{"d": "M 0 0 L 2 2", "onclick": "hack"}],
            [{"d": "M 0 0 L 2 2"}] * 25,
            [{"d": "M 0 0 L 2 2 " + "L 2 2 " * 500}],
        ]
        for strokes in bad:
            with self.subTest(strokes=repr(strokes)[:80]), self.assertRaises(ValueError):
                normalize_strokes(strokes)

    def test_rejects_missing_or_duplicate_slot(self):
        stroke = [{"d": "M 0 0 L 2 2"}]
        for source in ("<div></div>", SLOT + SLOT):
            with self.subTest(source=source[:40]), self.assertRaises(ValueError):
                inject_strokes(source, stroke)


if __name__ == "__main__":
    unittest.main()
