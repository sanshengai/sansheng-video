import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from production_timeline import export, digest
from render_production import verify, render, inventory, check_review
from production_sound_review import current_plan


class RenderReceiptTests(unittest.TestCase):
    def test_old_render_is_invalid_after_source_recompile_runtime_or_output_change(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            source = root / 'timeline.json'
            data = {'fps': 30, 'duration': 2, 'canvas': [1280, 720], 'requires_audio': False,
                    'shots': [{'id': 'a', 'start': 0, 'end': 2}],
                    'events': [{'id': 'a', 'scene_id': 'a', 'start': 0, 'end': 2,
                                'visual': {'type': 'box'}, 'timing_basis': 'authored'}]}
            source.write_text(json.dumps(data))
            export(source, root / 'derived')
            build = root / 'derived/production-build.json'
            runtime_root = root / 'runtime-tree'
            runtime_root.mkdir()
            output, runtime = root / 'draft.mp4', runtime_root / 'runtime.bin'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=s=160x90:r=30:d=2',
                            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(output)], check=True)
            runtime.write_bytes(b'test runtime fingerprint')
            receipt = root / 'draft.render.json'
            receipt.write_text(json.dumps({'kind': 'production-render/1', 'build_path': str(build),
                'build_sha256': digest(build), 'output': str(output), 'output_sha256': digest(output),
                'sound_review_plan_sha256': current_plan(build)[1], 'verification': {'has_audio': False},
                'host': {'system': platform.system(), 'release': platform.release(), 'machine': platform.machine()},
                'runtime_roots': [str(runtime_root)], 'runtime_files': {str(runtime): digest(runtime)}}))
            self.assertEqual('current_not_reviewed', verify(receipt)['status'])
            review = root / 'final-review.json'
            review.write_text(json.dumps({'approved': True, 'output_sha256': digest(output),
                'production_build_sha256': digest(build), 'render_receipt_sha256': digest(receipt)}))
            self.assertEqual('review_binding_current', check_review(root, output, review)['status'])
            for path in (runtime, output, source):
                before = path.read_bytes()
                path.write_bytes(before + b' ')
                with self.subTest(path=path), self.assertRaises(ValueError):
                    verify(receipt)
                with self.assertRaises(ValueError):
                    check_review(root, output, review)
                path.write_bytes(before)
            added = runtime_root / 'new-code.js'
            added.write_text('new dependency')
            with self.assertRaisesRegex(ValueError, 'runtime tree changed'):
                verify(receipt)
            added.unlink()
            runtime.unlink()
            with self.assertRaises(ValueError):
                verify(receipt)
            runtime.write_bytes(b'test runtime fingerprint')
            data['events'][0]['visual']['type'] = 'changed-box'
            source.write_text(json.dumps(data))
            export(source, root / 'derived', refresh=True)
            with self.assertRaisesRegex(ValueError, 'build changed'):
                verify(receipt)

    def test_runtime_inventory_rejects_empty_tree_and_external_link(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            tree = root / 'runtime'
            tree.mkdir()
            with self.assertRaisesRegex(ValueError, 'empty runtime'):
                inventory([tree])
            outside = root / 'external.js'
            outside.write_text('dependency')
            (tree / 'linked.js').symlink_to(outside)
            with self.assertRaisesRegex(ValueError, 'unsupported symlink'):
                inventory([tree])

    def test_symlink_output_rejected_before_any_render(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            target = root / "original.mp4"
            target.write_bytes(b"preserve")
            link = root / "out.mp4"
            link.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "symlinks"):
                render(root, root / "timeline.json", root / "runtime", root / "browser", link, refresh=True)
            self.assertEqual(b"preserve", target.read_bytes())

    def test_empty_build_rejected_before_renderer_runs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            (root / 'derived').mkdir()
            (root / 'derived/production-build.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'missing build evidence'):
                render(root, root / 'timeline.json', root / 'missing-runtime', root / 'missing-browser', root / 'out.mp4')


if __name__ == '__main__':
    unittest.main()
