#!/usr/bin/env python3
"""Diagnose core dependencies, or configure optional local branding without keys."""
from pathlib import Path
import argparse, importlib.util, json, os, shutil, subprocess, sys
ROOT = Path(__file__).resolve().parent

def profile(path=None):
    value = path or os.environ.get("SANSHENG_VIDEO_PROFILE_DIR")
    if not value and (ROOT / "profile").exists():
        value = ROOT / "profile"  # User-created, gitignored local profile/link.
    if not value:
        return None
    root = Path(value).expanduser().resolve()
    data = json.loads((root / "profile.json").read_text())
    if not isinstance(data, dict):
        raise ValueError("profile.json must be an object")
    for key in ("content_rules", "asset_roots"):
        if key in data and not isinstance(data[key], list):
            raise ValueError(key + " must be an array")
    if "brand" in data and not isinstance(data["brand"], dict):
        raise ValueError("brand must be an object")
    if data.get("brand", {}).get("logo"):
        logo = (root / data["brand"]["logo"]).resolve()
        if not logo.is_file():
            raise ValueError("brand logo missing")
    # Accept old profiles, but never expose retired library pointers to agents.
    for key in ("asset_roots", "cold_storage_root"):
        data.pop(key, None)
    return {"root": str(root), "configuration": data}

def check(runtime=None, browser=None, browser_checks=False):
    sys.path.insert(0, str(ROOT / "scripts"))
    from runtime_support import locate_renderer
    report = {"python": sys.version.split()[0], "tools": {}, "errors": []}
    if sys.version_info < (3, 10):
        report["errors"].append("Python >=3.10 required")
    for name in ("node", "ffmpeg", "ffprobe"):
        report["tools"][name] = shutil.which(name)
        if not report["tools"][name]:
            report["errors"].append(name + " missing")
    try:
        report["renderer"] = locate_renderer(runtime or os.environ.get("SANSHENG_VIDEO_RUNTIME"))
    except (ValueError, RuntimeError, OSError) as exc:
        report["errors"].append(str(exc))
    target = browser or os.environ.get("SANSHENG_VIDEO_BROWSER")
    if target and Path(target).expanduser().is_file() and os.access(Path(target).expanduser(), os.X_OK):
        report["browser"] = str(Path(target).expanduser().resolve())
    else:
        report["errors"].append("explicit executable browser path required: --browser")
    # Disabled optional modules are not inspected or reported.
    if browser_checks:
        report["browser_checks"] = bool(importlib.util.find_spec("playwright"))
        if not report["browser_checks"]:
            report["errors"].append("Playwright missing for explicitly enabled browser checks")
    try:
        loaded = profile()
        if loaded:
            report["profile"] = loaded["root"]
    except (ValueError, OSError) as exc:
        report["errors"].append("profile: " + str(exc))
    report["status"] = "ready" if not report["errors"] else "needs_setup"
    return report

def configure():
    if not sys.stdin.isatty():
        print("Interactive configuration: optional brand profile directory; no keys requested. Use --profile-dir for noninteractive validation, --check for core diagnosis.")
        return
    current = os.environ.get("SANSHENG_VIDEO_PROFILE_DIR")
    if current:
        print(json.dumps(profile(), ensure_ascii=False, indent=2))
        return
    answer = input("Enable a private brand/resource profile? [y/N] ").strip().lower()
    if answer not in ("y", "yes"):
        return
    target = Path(input("Profile directory: ").strip()).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    path = target / "profile.json"
    if not path.exists():
        path.write_text((ROOT / "profile.example/profile.json").read_text())
    profile(target)  # Read back, then record only the pointer locally.
    env = ROOT / ".env"
    if env.exists():
        raise ValueError(".env already exists; keep it and set SANSHENG_VIDEO_PROFILE_DIR manually")
    env.write_text("SANSHENG_VIDEO_PROFILE_DIR=" + json.dumps(str(target)) + "\n")
    print("Saved local profile pointer to .env; load it in your shell before use.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--runtime")
    parser.add_argument("--browser")
    parser.add_argument("--browser-checks", action="store_true")
    parser.add_argument("--profile-dir")
    parser.add_argument("--show-profile", action="store_true")
    args = parser.parse_args()
    try:
        if args.show_profile:
            print(json.dumps(profile(), ensure_ascii=False, indent=2))
        elif args.profile_dir:
            print(json.dumps(profile(args.profile_dir), ensure_ascii=False, indent=2))
        elif args.check:
            result = check(args.runtime, args.browser, args.browser_checks)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            sys.exit(bool(result["errors"]))
        else:
            configure()
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
