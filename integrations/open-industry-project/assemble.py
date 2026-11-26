"""Build the recorded fixture through OIP's real assembly command, never a second scene writer."""
import json
from pathlib import Path

from common import HERE, ROOT, execute, project_identity, verify_checkout

RECIPE_PATH = HERE / "examples/conveyor-native.json"


def assemble(checkout: Path, output: Path) -> dict:
    identity = verify_checkout(checkout)
    output = output.resolve()
    if output.is_relative_to(ROOT):
        raise ValueError("Generated OIP projects belong outside the PLC source checkout")
    if output.exists():
        raise ValueError("Output already exists; choose a new folder, no project was overwritten")
    recipe = json.loads(RECIPE_PATH.read_text())
    command = ["node", "scripts/add-part.mjs", str(output)]
    for part in recipe["parts"]:
        command += [part["package"], "--id", part["id"], "--at",
                    ",".join(str(x) for x in part["at"]), "--params", part["params"]]
    result = execute(command, cwd=checkout)
    if result.returncode:
        raise RuntimeError("OIP assembly failed: " + (result.stderr or result.stdout)[-3000:])
    validation = execute(["node", "scripts/validate-project.mjs", str(output), "--strict"], cwd=checkout)
    if validation.returncode:
        raise RuntimeError("Assembled OIP project did not validate: " + (validation.stderr + validation.stdout)[-3000:])
    return {"status": "passed", "scope": "OIP assembly and strict project loading only",
            "identity": identity, "project": str(output), "project_identity": project_identity(output),
            "parts": [part["id"] for part in recipe["parts"]],
            "assembly_log": result.stdout.strip(), "validation_log": validation.stdout.strip(),
            "native_execution": "not_run", "visual_render": "not_run"}
