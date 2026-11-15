import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import stem_kit as sk


class StemFormulaTests(unittest.TestCase):
    def test_formula_compiles_terms_fractions_radicals_and_escapes_html(self):
        html = sk.render_formula(
            r"{a2#a:a^2} + {b2#b:b^2} = {c2#c:\frac{50}{2}} = \sqrt{625} - 0",
            formula_id="pyth_eq",
        )
        self.assertIn('id="pyth_eq"', html)
        self.assertIn('data-term="a2"', html)
        self.assertIn('data-role="a"', html)
        self.assertIn('class="stem-frac"', html)
        self.assertIn('class="stem-sqrt"', html)
        self.assertIn("−", html)  # typographic minus

        escaped = sk.render_formula("x < y")
        self.assertIn("&lt;", escaped)
        self.assertNotIn("<y", escaped)

    def test_formula_rejects_empty_duplicate_terms_and_unknown_commands(self):
        for bad in (
            "",
            "   ",
            "{dup:x} + {dup:y}",
            "{bad id:x}",
            "{t#BAD:x}",
            "{empty:   }",
            r"\frca{1}{2}",
            r"\frac{}{2}",
            r"\sqrt{}",
            "{unclosed:x",
            "x + y}",
            "x^",
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                sk.render_formula(bad)


class StemGeometryAndSafeAreaTests(unittest.TestCase):
    def test_plane2d_equal_aspect_and_right_angle_orthogonality(self):
        plane = sk.Plane2D.create(
            [-4, 5],
            [-5, 4],
            [140, 280, 780, 780],
            canvas=[1080, 1920],
            equal_aspect=True,
        )
        self.assertAlmostEqual(plane.scale_x, plane.scale_y, places=9)
        p0 = plane.to_px(0, 0)
        px = plane.to_px(3, 0)
        py = plane.to_px(0, 4)
        self.assertAlmostEqual(px[0] - p0[0], 3 * plane.scale_x, places=6)
        self.assertAlmostEqual(p0[1] - py[1], 4 * plane.scale_y, places=6)

        ra = sk.svg_right_angle(plane, (0, 0), (0, 3), (4, 0))
        self.assertIn('class="stem-right-angle"', ra)

        # Mutation: non-right angle must be rejected.
        with self.assertRaisesRegex(ValueError, "并非直角"):
            sk.svg_right_angle(plane, (0, 0), (1, 3), (4, 0))

        # Mutation: non-uniform aspect scale must be rejected for right-angle marks.
        distorted = sk.Plane2D.create(
            [0, 10],
            [0, 5],
            [140, 280, 780, 780],
            canvas=[1080, 1920],
            equal_aspect=False,
        )
        with self.assertRaisesRegex(ValueError, "equal_aspect"):
            sk.svg_right_angle(distorted, (0, 0), (0, 3), (4, 0))

    def test_safe_area_rejects_overflow_without_explicit_reason(self):
        # Portrait 1080x1920 safe zone is x in [120, 940], y in [250, 1500].
        with self.assertRaisesRegex(ValueError, "超出安全区"):
            sk.Plane2D.create([0, 1], [0, 1], [80, 280, 800, 600], canvas=[1080, 1920])
        with self.assertRaisesRegex(ValueError, "超出安全区"):
            sk.Plane2D.create([0, 1], [0, 1], [140, 280, 820, 600], canvas=[1080, 1920])
        with self.assertRaisesRegex(ValueError, "超出安全区"):
            sk.Plane2D.create([0, 1], [0, 1], [140, 950, 700, 600], canvas=[1080, 1920])

        # Landscape 1920x1080 safe margin is >= 96 px on all four sides.
        with self.assertRaisesRegex(ValueError, "超出安全区"):
            sk.Plane2D.create([0, 1], [0, 1], [60, 120, 800, 700], canvas=[1920, 1080])

        # Explicit reason permits deliberate full-bleed background grid.
        allowed = sk.Plane2D.create(
            [0, 1],
            [0, 1],
            [60, 120, 800, 700],
            canvas=[1920, 1080],
            safe_override_reason="装饰性背景参考网格，不含关键文字与顶点",
        )
        self.assertEqual(allowed.viewport[0], 60.0)

    def test_primitives_axes_curve_polygon_dimension_and_vector(self):
        plane = sk.Plane2D.create([-2, 4], [-1, 5], [140, 300, 760, 760], canvas=[1080, 1920])
        self.assertIn('class="stem-axes"', sk.svg_axes(plane))
        curve = sk.svg_curve(plane, lambda x: 0.5 * x * x, -1.5, 2.5, traced=True)
        self.assertIn('pathLength="1000"', curve)
        poly = sk.svg_polygon(plane, [(0, 0), (3, 0), (0, 4)], fill="#E6F4F1")
        self.assertIn("<polygon", poly)
        dim = sk.svg_dimension_segment(plane, (0, 0), (3, 0), label="b = 3")
        self.assertIn("b = 3", dim)
        vec = sk.svg_vector_arrow(plane, (0, 0), (2, 3), label="F")
        self.assertIn('class="stem-vec"', vec)
        with self.assertRaises(ValueError):
            sk.svg_vector_arrow(plane, (1, 1), (0, 0))


class StemFactGateMutationTests(unittest.TestCase):
    def _valid_spec(self) -> dict:
        return {
            "equation_chains": [
                {
                    "variable": "x",
                    "steps": [
                        "3*x + 5 = 17",
                        "3*x = 17 - 5",
                        "3*x = 12",
                        "x = 12 / 3",
                        "x = 4",
                    ],
                    "solution": "4",
                }
            ],
            "right_triangles": [
                {
                    "vertices": {"C": [0, 0], "A": [0, 3], "B": [4, 0]},
                    "right_vertex": "C",
                    "claimed_squares": {"a2": 9, "b2": 16, "c2": 25},
                }
            ],
            "identities": [
                {
                    "equation": "a**2 + b**2 = c**2",
                    "cases": [
                        {"a": "3", "b": "4", "c": "5"},
                        {"a": "2.4", "b": "4.5", "c": "5.1"},
                        {"a": "3.6", "b": "2.7", "c": "4.5"},
                    ],
                },
                {
                    "equation": "0.5 * a * t**2 = s",
                    "cases": [{"a": "2", "t": "4", "s": "16"}],
                },
            ],
            "viewport_checks": [
                {
                    "canvas": [1080, 1920],
                    "viewport": [140, 300, 780, 780],
                    "domain_x": [-3.5, 5.5],
                    "domain_y": [-4.5, 4.5],
                    "equal_aspect": True,
                    "require_equal_aspect": True,
                    "world_points": [[0, 0], [0, 3], [4, 0], [-3, 3], [4, -4]],
                }
            ],
        }

    def test_valid_spec_passes_with_independent_counts(self):
        report = sk.verify_stem_spec(self._valid_spec())
        self.assertEqual(report["status"], "verified")
        self.assertEqual(
            report["checked"],
            {"equation_chains": 1, "right_triangles": 1, "identities": 2, "viewport_checks": 1},
        )
        self.assertEqual(report["total"], 5)

    def test_empty_inputs_are_refused(self):
        for empty in ({}, None, [], {"equation_chains": [], "identities": []}):
            with self.subTest(empty=empty), self.assertRaises(ValueError):
                sk.verify_stem_spec(empty)  # type: ignore[arg-type]

    def test_mutations_on_monitored_paths_fail(self):
        # Mutation 1: forgot to flip sign during transpose (+5 instead of -5)
        bad_sign = self._valid_spec()
        bad_sign["equation_chains"][0]["steps"][1] = "3*x = 17 + 5"
        with self.assertRaisesRegex(ValueError, "不等价"):
            sk.verify_stem_spec(bad_sign)

        # Mutation 2: wrong claimed solution
        bad_sol = self._valid_spec()
        bad_sol["equation_chains"][0]["solution"] = "5"
        with self.assertRaisesRegex(ValueError, "不一致"):
            sk.verify_stem_spec(bad_sol)

        # Mutation 3: degenerate 0*x = 0 step
        bad_deg = self._valid_spec()
        bad_deg["equation_chains"][0]["steps"].append("0*x = 0")
        with self.assertRaisesRegex(ValueError, "退化"):
            sk.verify_stem_spec(bad_deg)

        # Mutation 4: non-orthogonal right triangle
        bad_tri = self._valid_spec()
        bad_tri["right_triangles"][0]["vertices"]["A"] = [1, 3]
        with self.assertRaisesRegex(ValueError, "不是直角三角形"):
            sk.verify_stem_spec(bad_tri)

        # Mutation 5: claimed square area mismatch (9 + 16 != 24)
        bad_area = self._valid_spec()
        bad_area["right_triangles"][0]["claimed_squares"]["c2"] = 24
        with self.assertRaisesRegex(ValueError, "不一致"):
            sk.verify_stem_spec(bad_area)

        # Mutation 6: identity broken on one keyframe
        bad_ident = self._valid_spec()
        bad_ident["identities"][0]["cases"][1]["c"] = "5.2"
        with self.assertRaisesRegex(ValueError, "不成立"):
            sk.verify_stem_spec(bad_ident)

        # Mutation 7: world point projects outside portrait safe zone
        bad_pt = self._valid_spec()
        bad_pt["viewport_checks"][0]["world_points"].append([9.0, 0.0])
        with self.assertRaisesRegex(ValueError, "越出安全区"):
            sk.verify_stem_spec(bad_pt)

    def test_cli_exit_codes_for_valid_mutated_and_empty_files(self):
        cli = [sys.executable, str(ROOT / "scripts" / "stem_kit.py")]
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            good = tmp / "good.json"
            good.write_text(json.dumps(self._valid_spec()), encoding="utf-8")
            ok = subprocess.run(cli + ["verify", str(good)], capture_output=True, text=True)
            self.assertEqual(ok.returncode, 0, msg=ok.stderr)

            empty = tmp / "empty.json"
            empty.write_text("", encoding="utf-8")
            res_empty = subprocess.run(cli + ["verify", str(empty)], capture_output=True, text=True)
            self.assertEqual(res_empty.returncode, 1)

            bad = self._valid_spec()
            bad["equation_chains"][0]["steps"][2] = "3*x = 15"
            bad_file = tmp / "bad.json"
            bad_file.write_text(json.dumps(bad), encoding="utf-8")
            res_bad = subprocess.run(cli + ["verify", str(bad_file)], capture_output=True, text=True)
            self.assertEqual(res_bad.returncode, 1)

            assets = tmp / "assets"
            res_emit = subprocess.run(cli + ["emit-assets", str(assets)], capture_output=True, text=True)
            self.assertEqual(res_emit.returncode, 0)
            self.assertTrue((assets / "stem-math.css").is_file())
            self.assertTrue((assets / "stem-runtime.js").is_file())


if __name__ == "__main__":
    unittest.main()
