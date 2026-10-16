#!/usr/bin/env python3
"""Scan staged content without printing the matched private value."""
import argparse
from pathlib import Path
import re
import subprocess
import sys

RULES = {
    "personal-home": r"(?:/Users/[^/\s]+/|/home/[^/\s]+/|[A-Za-z]:\\Users\\[^\\\s]+\\)",
    "private-key": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "provider-token": r"\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|AIza[A-Za-z0-9_-]{30,})",
    "cloud-access-key": r"\bAKIA[A-Z0-9]{16}\b",
}


def staged_files(all_tracked=False):
    args = ["git", "ls-files", "-z"] if all_tracked else ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"]
    return [p.decode() for p in subprocess.check_output(args).split(b"\0") if p]


def scan(rules, all_tracked=False, exemptions=()):
    failed = []
    for name in staged_files(all_tracked):
        if name.startswith(".githooks/") or name in exemptions:
            continue
        result = subprocess.run(["git", "show", ":" + name], capture_output=True)
        if result.returncode:
            raise RuntimeError("cannot inspect staged file: " + name)
        data = result.stdout
        if b"\0" in data:
            continue
        content = data.decode("utf-8", errors="replace")
        for label, pattern in rules.items():
            if re.search(pattern, content):
                failed.append((name, label))
    for name, label in failed:
        print(f"redact guard: {name}: {label}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="scan every indexed file")
    args = parser.parse_args()
    sys.exit(scan(RULES, args.all))
