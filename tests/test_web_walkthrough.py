import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import production_timeline
import web_walkthrough


@unittest.skipUnless(shutil.which("node"), "Node required for capture adapter")
class WebWalkthroughTests(unittest.TestCase):
    def fixture(self, root):
        from PIL import Image
        Image.new("RGB", (640, 360), "#18332b").save(root / "fixture.png")
        driver = root / "capture-fixture.mjs"
        driver.write_text('''import fs from 'node:fs/promises';
import {captureWebState} from ''' + json.dumps((SCRIPTS / "capture_web_state.mjs").as_uri()) + ''';
const page = {
 evaluate: async () => ({url:'https://example.org/product',viewport:[640,360],scroll:[0,0],dpr:1,
  controls:{save:{selector:'#save',rect:[10,20,80,30],text:'Save default',value:null,href:null},
            status:{selector:'#status',rect:[10,80,180,30],text:'Saved in this browser',value:null,href:null}}}),
 screenshot: async () => fs.readFile(new URL('./fixture.png', import.meta.url))
};
for (const id of ['before','after']) await captureWebState(page,{output:new URL('./'+id+'.json',import.meta.url).pathname,
 id,controls:{save:'#save',status:'#status'}});
''')
        subprocess.run(["node", str(driver)], check=True, capture_output=True)
        task = {"kind": "web-walkthrough/1", "task": "Choose a default and hand it to the assistant",
                "states": ["before.json", "after.json"], "steps": [{"id": "save", "before": "before", "after": "after",
                "control": "save", "control_text": "Save default", "scope": "browser_local",
                "feedback_control": "status", "result": "Saved in this browser",
                "next_step": "Copy these defaults to the assistant to configure its skill"}]}
        task_file = root / "task.json"
        task_file.write_text(json.dumps(task))
        brief = {"kind": "promotion-brief/1", "mode": "walkthrough", "audience": "New users", "promise": "Set defaults",
                 "title": "Choose your style", "destination": "Product page", "claims": [
                     {"id": "defaults", "benefit": "Keep selections", "evidence_ids": ["task"]}],
                 "evidence": [{"id": "task", "file": "task.json", "kind": "web-walkthrough",
                               "sha256": hashlib.sha256(task_file.read_bytes()).hexdigest(),
                               "version": "capture-one", "acquired_at": "2026-01-01T00:00:00Z"}]}
        (root / "brief.json").write_text(json.dumps(brief))
        timeline = {"fps": 30, "duration": 4, "canvas": [1280, 720], "requires_audio": False,
                    "promotion": "brief.json", "shots": [{"id": "one", "start": 0, "end": 4}],
                    "events": [{"id": "save", "scene_id": "one", "start": 0, "end": 4,
                                "timing_basis": "authored", "visual": {"type": "web-state"}, "claim_ids": ["defaults"]}]}
        source = root / "timeline.json"
        source.write_text(json.dumps(timeline))
        return source, task_file, task

    def test_capture_adapter_roundtrip_and_build_dependency_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, _, _ = self.fixture(root)
            production_timeline.export(source, root / "derived")
            plan = json.loads((root / "derived/promotion-plan.json").read_text())
            self.assertIn("Saved in this browser", json.dumps(plan))
            state = root / "before.json"
            data = json.loads(state.read_text())
            data["viewport"] = [640, 359]
            state.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "stale"):
                production_timeline.check(root / "derived/production-build.json")
            with self.assertRaisesRegex(ValueError, "context changed"):
                production_timeline.export(source, root / "derived", refresh=True)

    def test_missing_control_wrong_text_unproven_copy_and_empty_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, path, task = self.fixture(root)
            for change in (lambda d: d.update(states=[]), lambda d: d.update(steps=[]),
                           lambda d: d["steps"][0].update(control="invented"),
                           lambda d: d["steps"][0].update(control_text="Apply to local skill now"),
                           lambda d: d["steps"][0].update(scope="clipboard"),
                           lambda d: d["steps"][0].pop("next_step")):
                altered = copy.deepcopy(task)
                change(altered)
                path.write_text(json.dumps(altered))
                with self.assertRaises(ValueError):
                    web_walkthrough.resolve(path)
            path.write_text(json.dumps(task))
            (root / "after.png").unlink()
            with self.assertRaisesRegex(ValueError, "missing or changed"):
                web_walkthrough.resolve(path)


if __name__ == "__main__":
    unittest.main()
