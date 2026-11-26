#!/usr/bin/env python3
"""Install OIP at one reviewed commit, outside plc-workspace; never update existing source."""
import argparse
import json
from pathlib import Path
import subprocess

from common import INDEX, ROOT, checkout_path, verify_checkout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path)
    args = parser.parse_args()
    target = checkout_path(args.checkout)
    if target.is_relative_to(ROOT):
        parser.error("OIP checkout must be outside plc-workspace; it is not vendored")
    if target.exists() and not (target / ".git").exists():
        parser.error("Existing target is not an OIP git checkout; no files were replaced")
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--no-checkout", "--filter=blob:none", "--depth", "1",
                        INDEX["repository"], str(target)], check=True, timeout=300)
        subprocess.run(["git", "fetch", "--depth", "1", "origin", INDEX["commit"]],
                       cwd=target, check=True, timeout=300)
        subprocess.run(["git", "checkout", "--detach", INDEX["commit"]],
                       cwd=target, check=True, timeout=300)
    verify_checkout(target, dependencies=False)
    subprocess.run(["npm", "ci", "--no-audit", "--no-fund"], cwd=target, check=True, timeout=600)
    print(json.dumps({"status": "ready", "checkout": str(target),
                      "identity": verify_checkout(target)}, indent=2))


if __name__ == "__main__":
    main()
