"""Identity and process helpers for the optional, pinned OIP installation."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
INDEX = json.loads((HERE / "source-index.json").read_text())


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def checkout_path(value: str | Path | None = None) -> Path:
    chosen = value or os.environ.get("PLC_OIP_CHECKOUT") or os.environ.get("PLC_OIP_DIR")
    if chosen:
        return Path(chosen).expanduser().resolve()
    return (Path.home() / ".cache" / "plc-workspace" / "oip" / INDEX["commit"]).resolve()


def execute(argv: list[str], *, cwd: Path, timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                          check=False, env={**os.environ, "NO_COLOR": "1"})


def verify_checkout(checkout: Path, *, dependencies: bool = True) -> dict:
    if not (checkout / ".git").exists():
        raise FileNotFoundError("Pinned OIP checkout missing; run setup.py first")
    head = execute(["git", "rev-parse", "HEAD"], cwd=checkout, timeout=15)
    if head.returncode or head.stdout.strip() != INDEX["commit"]:
        raise ValueError("OIP HEAD differs from source-index.json; refusing unpinned execution")
    dirty = execute(["git", "status", "--porcelain", "--untracked-files=all"], cwd=checkout, timeout=15)
    if dirty.returncode or dirty.stdout.strip():
        raise ValueError("OIP source changed or contains untracked source; use a clean pinned checkout")
    for relative, digest in INDEX["files_sha256"].items():
        if sha256((checkout / relative).read_bytes()) != digest:
            raise ValueError(f"Pinned OIP file digest changed: {relative}")
    node = shutil.which("node")
    if not node:
        raise FileNotFoundError("Node.js 24 or newer is required")
    version = execute([node, "--version"], cwd=checkout, timeout=15).stdout.strip()
    if int(version.lstrip("v").split(".")[0]) < INDEX["node_major_minimum"]:
        raise ValueError("Pinned OIP requires Node.js 24 or newer")
    if dependencies and not (checkout / "node_modules/vite/package.json").is_file():
        raise FileNotFoundError("OIP dependencies missing; run setup.py first")
    return {"repository": INDEX["repository"], "commit": INDEX["commit"],
            "package_lock_sha256": INDEX["files_sha256"]["package-lock.json"],
            "node": version, "source_clean": True}


def project_identity(folder: Path) -> dict:
    files = {}
    for path in sorted(folder.rglob("*")):
        if path.is_file() and path.suffix in {".json", ".js", ".ts", ".st"}:
            files[path.relative_to(folder).as_posix()] = sha256(path.read_bytes())
    return {"sha256": sha256(json.dumps(files, sort_keys=True).encode()), "files": files}


def base_report(check: str, scope: str) -> dict:
    return {"schema": "plc-oip-result/v1", "check": check, "scope": scope,
            "status": "not_run", "upstream_commit": INDEX["commit"],
            "siemens_acceptance": "not_run", "hardware_acceptance": "not_run"}
