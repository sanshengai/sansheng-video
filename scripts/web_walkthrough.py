#!/usr/bin/env python3
"""Validate captured webpage states and a task; never invent controls or feedback."""
import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
from urllib.parse import urlparse


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def present(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}: nonempty text required")
    return value


def finite_numbers(value, count, label):
    if not isinstance(value, list) or len(value) != count or any(
            type(v) not in {int, float} or not math.isfinite(v) for v in value):
        raise ValueError(f"{label}: expected {count} finite numbers")
    return value


def state(source):
    source = Path(source).resolve()
    raw = source.read_bytes()
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get("kind") != "web-state/1":
        raise ValueError("expected web-state/1")
    present(data.get("id"), "state.id")
    url = urlparse(present(data.get("url"), "state.url"))
    if url.scheme not in {"http", "https"} or not url.netloc:
        raise ValueError("invalid state URL")
    captured = datetime.fromisoformat(present(data.get("captured_at"), "captured_at").replace("Z", "+00:00"))
    if captured.tzinfo is None:
        raise ValueError("captured_at requires timezone")
    viewport = finite_numbers(data.get("viewport"), 2, "viewport")
    finite_numbers(data.get("scroll"), 2, "scroll")
    dpr = data.get("dpr")
    if type(dpr) not in {int, float} or not math.isfinite(dpr) or dpr <= 0 or min(viewport) <= 0:
        raise ValueError("invalid viewport/dpr")
    image = (source.parent / present(data.get("image"), "state.image")).resolve()
    if not image.is_file() or digest(image) != data.get("image_sha256"):
        raise ValueError("screenshot missing or changed")
    from PIL import Image
    with Image.open(image) as picture:
        if any(abs(actual - css * dpr) > 1 for actual, css in zip(picture.size, viewport)):
            raise ValueError("screenshot dimensions do not match viewport/dpr")
        picture.verify()
    context = {key: data[key] for key in ("url", "viewport", "scroll", "dpr", "image_sha256")}
    checksum = hashlib.sha256(json.dumps(context, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    if checksum != data.get("context_sha256"):
        raise ValueError("state context changed; recapture screenshot and controls")
    controls = data.get("controls")
    if not isinstance(controls, dict):
        raise ValueError("controls must be an object")
    for ident, control in controls.items():
        present(ident, "control id")
        present(control.get("selector"), "control.selector")
        x, y, width, height = finite_numbers(control.get("rect"), 4, "control.rect")
        if width <= 0 or height <= 0 or x >= viewport[0] or y >= viewport[1] or x + width <= 0 or y + height <= 0:
            raise ValueError("target outside captured viewport; scroll and recapture")
        if control.get("context_sha256") != checksum:
            raise ValueError("control belongs to another state context")
    if data.get("method") != "real_state_synthetic_camera":
        raise ValueError("declare capture method accurately")
    return {**data, "image": str(image)}, {str(source): hashlib.sha256(raw).hexdigest(), str(image): digest(image)}


def resolve(source):
    source = Path(source).resolve()
    raw = source.read_bytes()
    task = json.loads(raw)
    if not isinstance(task, dict) or task.get("kind") != "web-walkthrough/1":
        raise ValueError("expected web-walkthrough/1")
    present(task.get("task"), "task")
    states, inputs = {}, {str(source): hashlib.sha256(raw).hexdigest()}
    if not isinstance(task.get("states"), list) or not task["states"]:
        raise ValueError("task needs captured states")
    for relative in task["states"]:
        data, dependencies = state(source.parent / present(relative, "state file"))
        if data["id"] in states:
            raise ValueError("duplicate state id")
        states[data["id"]] = data
        inputs.update(dependencies)
    steps = task.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("task needs observed steps")
    ids = set()
    for step in steps:
        ident = present(step.get("id"), "step.id")
        if ident in ids:
            raise ValueError("duplicate step id")
        ids.add(ident)
        if step.get("before") not in states or step.get("after") not in states:
            raise ValueError("step references unknown captured state")
        before, after = states[step["before"]], states[step["after"]]
        control = before["controls"].get(step.get("control"))
        if control is None:
            raise ValueError("step control absent from before state")
        if step.get("control_text") != control.get("text") or not step.get("control_text"):
            raise ValueError("button text mismatch or empty label")
        if step.get("scope") not in {"clipboard", "browser_local", "server", "agent_handoff", "navigation", "view"}:
            raise ValueError("declare actual result scope")
        present(step.get("result"), "step.result")
        if step["scope"] in {"clipboard", "agent_handoff"}:
            copied = after.get("copied")
            if not isinstance(copied, dict) or not copied.get("text") or copied.get("method") not in {
                    "intercepted_writeText", "observed_copy_result"}:
                raise ValueError("copy/handoff needs captured copied text")
        else:
            feedback = after["controls"].get(step.get("feedback_control"))
            if feedback is None or not feedback.get("text"):
                raise ValueError("step needs actual visible feedback control/text")
        if step["scope"] == "browser_local":
            present(step.get("next_step"), "browser-local result needs its next-step boundary")
    for path, checksum in inputs.items():
        if digest(path) != checksum:
            raise ValueError("capture changed during resolution")
    return {**task, "states": states, "status": "captured_not_live_or_semantic_approval"}, inputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", type=Path)
    args = parser.parse_args()
    result, inputs = resolve(args.task)
    print(json.dumps({"task": result["task"], "states": len(result["states"]),
                      "steps": len(result["steps"]), "status": result["status"], "inputs": inputs}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
