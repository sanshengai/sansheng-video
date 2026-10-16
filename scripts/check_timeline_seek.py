#!/usr/bin/env python3
"""Offline GSAP timeline seek audit. A technical pass is not human approval."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import mimetypes
import platform
from pathlib import Path
import subprocess
import threading
from urllib.parse import unquote, urlsplit


def sha(data):
    return hashlib.sha256(data).hexdigest()


def browser_executable(pid):
    """Observe the running process; a requested launch path is not evidence."""
    if type(pid) is not int or pid <= 0:
        raise ValueError("invalid browser process id")
    if platform.system() == "Darwin":
        lib = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        lib.proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        lib.proc_pidpath.restype = ctypes.c_int
        buffer = ctypes.create_string_buffer(4096)
        if lib.proc_pidpath(pid, buffer, len(buffer)) <= 0:
            raise ValueError("cannot observe browser executable with proc_pidpath")
        value = buffer.value.decode()
    else:
        proc = Path(f"/proc/{pid}/exe")
        value = str(proc.resolve()) if proc.exists() else subprocess.check_output(
            ["ps", "-p", str(pid), "-o", "comm="], text=True, timeout=5).strip()
    if not value or not Path(value).is_absolute() or not Path(value).is_file():
        raise ValueError("cannot establish actual browser executable")
    return Path(value).resolve()


def evaluate_data(page, expression, arg=None):
    """Reject thenables before Playwright can await a GSAP timeline forever.

    Only synchronous data expressions belong here. Asynchronous readiness uses
    wait_for_function with an explicit timeout below.
    """
    return page.evaluate("arg => { const value = (" + expression + " )(arg); "
                         "if (value && typeof value.then === 'function') "
                         "throw new Error('thenable result forbidden: return plain data or void'); "
                         "return value; }", arg)


def check(index, output, times, canvas=(640, 360), root="root", timeout=10000, browser_path=None):
    from playwright.sync_api import sync_playwright

    index, output = Path(index).resolve(), Path(output).resolve()
    if not index.is_file():
        raise ValueError("index must be an existing local HTML file")
    if not times or any(type(t) not in (int, float) or not math.isfinite(t) or t < 0 for t in times):
        raise ValueError("times must be nonempty finite nonnegative seconds")
    if len(canvas) != 2 or any(type(x) is not int or not 1 <= x <= 8192 for x in canvas):
        raise ValueError("canvas must contain two integer dimensions in 1..8192")
    if not isinstance(root, str) or not root or timeout <= 0:
        raise ValueError("root and positive timeout required")
    if browser_path is not None:
        browser_path = Path(browser_path).expanduser().resolve()
        if not browser_path.is_file():
            raise ValueError("browser must be an existing Chromium executable")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("QA output must be a new or empty directory; refusing overwrite")
    output.mkdir(parents=True, exist_ok=True)
    report = {"kind": "timeline-seek-check/1", "status": "failed", "root": root,
              "times": sorted(set(times)), "canvas": list(canvas), "inputs": {},
              "screenshots": [], "errors": [], "mismatches": [],
              "scope": "sampled same-environment PNG equality; not visual/audio approval"}
    inputs, errors = report["inputs"], report["errors"]
    inputs[str(Path(__file__).resolve())] = sha(Path(__file__).read_bytes())
    base = index.parent

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            target = (base / unquote(urlsplit(self.path).path).lstrip("/")).resolve()
            if not target.is_relative_to(base) or not target.is_file():
                errors.append("missing/forbidden local resource: " + self.path)
                self.send_error(404)
                return
            data = target.read_bytes()
            digest = sha(data)
            if str(target) in inputs and inputs[str(target)] != digest:
                errors.append("input changed while reading: " + str(target))
            inputs[str(target)] = digest
            self.send_response(200)
            self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    # Quote the actual filename, including spaces/non-ASCII; serve only index's directory.
    from urllib.parse import quote
    url = origin + "/" + quote(index.name)
    try:
        with sync_playwright() as pw:
            launch_options = {"headless": True}
            if browser_path is not None:
                launch_options["executable_path"] = str(browser_path)
            browser = pw.chromium.launch(**launch_options)
            # Chromium's advertised default executable can differ from the headless
            # shell actually launched. Observe the browser process, not a cache guess.
            session = browser.new_browser_cdp_session()
            processes = session.send("SystemInfo.getProcessInfo")["processInfo"]
            pid = next(row["id"] for row in processes if row["type"] == "browser")
            actual_executable = browser_executable(pid)
            report["browser"] = {"name": "chromium", "version": browser.version,
                                 "executable": str(actual_executable),
                                 "requested_executable": str(browser_path) if browser_path else None}
            session.detach()

            def page_new():
                context = browser.new_context(viewport={"width": canvas[0], "height": canvas[1]},
                                              device_scale_factor=1, service_workers="block")

                def route(request_route):
                    address = urlsplit(request_route.request.url)
                    if address.scheme == "http" and address.netloc == urlsplit(origin).netloc:
                        request_route.continue_()
                    else:
                        errors.append("blocked external resource: " + request_route.request.url)
                        request_route.abort()

                context.route("**/*", route)
                def block_socket(socket):
                    errors.append("blocked websocket: " + socket.url)
                    socket.close()
                context.route_web_socket("**/*", block_socket)
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append("pageerror: " + str(error)))
                page.on("console", lambda msg: errors.append("console: " + msg.text) if msg.type == "error" else None)
                page.on("requestfailed", lambda request: errors.append("requestfailed: " + request.url))
                page.on("response", lambda response: errors.append(f"HTTP {response.status}: {response.url}") if response.status >= 400 else None)
                # Metadata-preloaded media can keep a Chromium request open after
                # suspending its download. Network silence is not resource readiness.
                page.goto(url, wait_until="load", timeout=timeout)
                evaluate_data(page, """() => {
                    for (const media of document.querySelectorAll('audio,video')) {
                        if (media.getAttribute('src') || media.querySelector('source[src]')) {
                            media.preload = 'auto';
                            if (media.networkState === HTMLMediaElement.NETWORK_EMPTY) media.load();
                        }
                    }
                }""")
                page.wait_for_function("""async () => {
                    const ready = window.productionReady;
                    if (ready && typeof ready.then === 'function') {
                        await ready;
                    } else if (ready !== undefined && ready !== true) return false;
                    await document.fonts.ready;
                    for (const image of document.images) {
                        if (!image.complete) return false;
                        if (!image.naturalWidth) throw new Error('image unavailable: ' + image.src);
                        await image.decode();
                    }
                    for (const media of document.querySelectorAll('audio,video')) {
                        if (!media.getAttribute('src') && !media.querySelector('source[src]')) continue;
                        if (media.error) throw new Error('media unavailable: ' + media.currentSrc +
                                                        ' (code ' + media.error.code + ')');
                        if (media.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) return false;
                        if (!Number.isFinite(media.duration) || media.duration <= 0)
                            throw new Error('media has no finite positive duration: ' + media.currentSrc);
                    }
                    return true;
                }""", timeout=timeout)
                page.wait_for_function("key => !!(window.gsap && window.__timelines && window.__timelines[key] instanceof gsap.core.Timeline)", arg=root, timeout=timeout)
                details = evaluate_data(page, "key => {const t=window.__timelines[key]; return {gsap:gsap.version,duration:t.duration()};}", root)
                report["gsap_version"] = details["gsap"]
                if max(times) > details["duration"]:
                    context.close()
                    raise ValueError("sample time exceeds actual root timeline duration")
                evaluate_data(page, "key => {window.__timelines[key].pause(); gsap.ticker.sleep();}", root)
                return context, page

            def capture(page, mode, number, t):
                # suppressEvents=false exercises callbacks that can hide state accumulation.
                evaluate_data(page, "args => {window.__timelines[args.root].seek(args.time, false); gsap.ticker.sleep();}", {"root": root, "time": t})
                destination = output / f"{mode}-{number:03d}.png"
                data = page.screenshot(path=str(destination), type="png", timeout=timeout)
                record = {"mode": mode, "time": t, "path": str(destination), "sha256": sha(data)}
                report["screenshots"].append(record)
                return record

            ordered = sorted(set(times))
            context, page = page_new()
            expected = {t: capture(page, "forward", i, t)["sha256"] for i, t in enumerate(ordered)}
            for i, t in enumerate(reversed(ordered)):
                capture(page, "reverse", i, t)
            context.close()
            for i, t in enumerate(ordered):
                context, page = page_new()
                capture(page, "cold", i, t)
                context.close()
            browser.close()
            report["mismatches"] = [r for r in report["screenshots"] if r["sha256"] != expected[r["time"]]]
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    for name, expected_hash in inputs.items():
        target = Path(name)
        if not target.is_file() or sha(target.read_bytes()) != expected_hash:
            errors.append("input changed during audit: " + name)
    if not errors and not report["mismatches"] and len(report["screenshots"]) == 3 * len(set(times)):
        report["status"] = "passed"
    (output / "seek-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path)
    parser.add_argument("--out", type=Path, required=True, help="new/empty project QA directory")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--times", help="comma-separated seconds")
    group.add_argument("--times-json", type=Path, help="array or {times:[...],canvas:[w,h]}")
    parser.add_argument("--size", help="WIDTHxHEIGHT (otherwise JSON canvas or 640x360)")
    parser.add_argument("--root", default="root", help="key in window.__timelines")
    parser.add_argument("--timeout-ms", type=int, default=10000)
    parser.add_argument("--browser", type=Path, help="explicit installed Chromium executable (default: Playwright)")
    args = parser.parse_args()
    try:
        source_bytes = args.times_json.read_bytes() if args.times_json else None
        source = json.loads(source_bytes) if source_bytes is not None else [float(x) for x in args.times.split(",")]
        times = source.get("times") if isinstance(source, dict) else source
        canvas = [int(x) for x in args.size.lower().split("x")] if args.size else (source.get("canvas", [640, 360]) if isinstance(source, dict) else [640, 360])
        report = check(args.index, args.out, times, canvas, args.root, args.timeout_ms, args.browser)
        if args.times_json:
            report["inputs"][str(args.times_json.resolve())] = sha(source_bytes)
            if args.times_json.read_bytes() != source_bytes:
                report["status"] = "failed"
                report["errors"].append("times JSON changed during audit")
            (args.out / "seek-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"status": report["status"], "report": str(args.out / "seek-report.json"), "errors": report["errors"], "mismatch_count": len(report["mismatches"])}, ensure_ascii=False))
        return 0 if report["status"] == "passed" else 1
    except (ValueError, OSError, TypeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
