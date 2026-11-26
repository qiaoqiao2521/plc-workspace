"""Reviewable folder bundle: original OIP parts, frozen native source, optional exact evidence."""
import json
from pathlib import Path
import tempfile
import zipfile

from assemble import RECIPE_PATH, assemble
from common import HERE, ROOT, base_report, project_identity, sha256, verify_checkout


def export_bundle(checkout: Path, output: Path, *, project: Path | None = None,
                  program: dict | None = None, report: dict | None = None) -> dict:
    identity = verify_checkout(checkout)
    output = output.resolve()
    if output.is_relative_to(ROOT) or output.exists():
        raise ValueError("Choose a new export file outside the PLC source checkout")
    recipe = json.loads(RECIPE_PATH.read_text())
    if program is None:
        source = ROOT / recipe["native_source"]
        program = {"profile": "conveyor-8-demo-v1", "source": source.read_text(), "filename": source.name}
    from native_bridge import _load_core
    profile, _ = _load_core().prepare_program(program)
    if profile["id"] not in {"conveyor-8-demo-v1", "conveyor-12-v1"}:
        raise ValueError("This OIP fixture exports only the two conveyor profiles")
    source_hash = sha256(program["source"].encode())
    with tempfile.TemporaryDirectory(prefix="plc-oip-export-") as tmp:
        if project is None:
            project = Path(tmp) / "plant"
            assemble(checkout, project)
        project_id = project_identity(project)
        if not project_id["files"] or "scene.json" not in project_id["files"]:
            raise ValueError("Export requires an assembled OIP project")
        if report is not None and (
            report.get("schema") != "plc-oip-result/v1" or report.get("check") != "native-oip-loop"
            or report.get("source_sha256") != source_hash
            or report.get("profile") != profile["id"]
            or report.get("upstream_commit") != identity["commit"]
            or report.get("project_identity") != project_id
        ):
            raise ValueError("Evidence does not match this source, profile, pinned OIP and project")
        files = {"project/" + relative: (project / relative).read_bytes() for relative in project_id["files"]}
        if any(sha256(files["project/" + name]) != digest for name, digest in project_id["files"].items()):
            raise RuntimeError("Project changed while capturing export")
        metadata = {"schema": "plc-oip-export/v1", "identity": identity, "project_identity": project_id,
                    "profile": profile["id"], "source_sha256": source_hash,
                    "bindings": recipe["bindings"], "physics_hz": recipe["physics_hz"], "scan_ms": recipe["scan_ms"],
                    "native_execution": report["status"] if report else "not_run",
                    "siemens_acceptance": "not_run", "hardware_acceptance": "not_run"}
        files.update({
            "binding.json": (json.dumps(metadata, ensure_ascii=False, indent=2) + "\n").encode(),
            "native/program.json": (json.dumps(program, ensure_ascii=False, indent=2) + "\n").encode(),
            "native/source.scl": program["source"].encode(),
            "source-index.json": (HERE / "source-index.json").read_bytes(),
            "LICENSE.OIP": (checkout / "LICENSE").read_bytes(),
            "THIRD_PARTY_NOTICES.OIP.md": (checkout / "THIRD_PARTY_NOTICES.md").read_bytes(),
            "README.txt": (
                "Open project/ in the pinned Open Industry Project workbench to inspect the physical scene.\n"
                "There is deliberately no second OIP PLC program in project/. Native PLC scans are owned by\n"
                "plc-workspace's integrations/open-industry-project bridge. Run native-test with --project\n"
                "pointing to this project/ and --program-json pointing to native/program.json.\n"
                "binding.json records the source and plant identities. Optional evidence/native.json records\n"
                "the actual original-source run and an explicitly synthetic negative controller.\n"
                "Opening the scene or replaying evidence does not establish a new verification result.\n"
                "OIP parts are MIT licensed; see LICENSE.OIP and THIRD_PARTY_NOTICES.OIP.md.\n"
                "This bundle contains no Siemens, PLCSIM, hardware, safety or physical-calibration acceptance.\n"
            ).encode(),
        })
        if report is not None:
            files["evidence/native.json"] = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode()
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(files.items()):
                archive.writestr(name, data)
    return {**base_report("oip-export", "Reviewable OIP project/native source/evidence bundle"), "status": "passed",
            "output": str(output), "sha256": sha256(output.read_bytes()), "files": len(files),
            "project_identity": project_id, "source_sha256": source_hash,
            "native_execution": report["status"] if report else "not_run", "visual_render": "not_run"}
