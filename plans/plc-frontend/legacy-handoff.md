# Whole-repository closeout inventory — 2026-09-30

Owner for retained items: root Codex in this repository. None deleted or assumed abandoned. These are pre-existing items observed before frontend edits, not new web assets.

| Group | Evidence / decision | Shortest next acceptance entry |
| --- | --- | --- |
| Four staged `container/*` executable bits | Dated CURRENT_STATE reports Linux Permission denied; all have interpreter shebangs. Syntax and executable mode checked; integrate the four mode-only changes. No container-runtime acceptance claimed. | Existing container wrappers and Docker build entry |
| `CURRENT_STATE.md` | Recovery snapshot dated 2026-09-15 still describes old account, missing dependencies and old state. Preserve locally; PROJECT.md remains current. | Reconcile every claim against current PROJECT, Dockerfile and tool versions before publishing a dated archival note. |
| `docs/harness/` plus garbled-name `PLC…` material directory | Harness README refers to `PLC素材库/manifest.yaml`; actual extracted directory name is corrupted. Material provenance and redistribution boundary not verified; automatic publication could publish specialist material and broken entry links. | Restore filename mapping in an isolated copy, verify source/redistribution scope and links, then reconcile harness instructions with AGENTS. |
| `projects/FB_MainSequence/05_tia_sync/{mapping.yaml,final_import_notes.md,post_sync_checklist.md}` | Mapping contains absolute `E:/web/plc-workspace` paths and permits checker_adapter_constants, contrary to current non-abstraction rule. No selected TIA/CPU target. | Compare with scan-contract v0.3 and current sync generator; remove obsolete mapping assumptions before Windows acceptance. |
| `projects/FB_MainSequence/03_checks/test_vectors/` | Existing imported vector assets are not connected to current compiled-ST test runner; do not imply they are tested. | Map vectors to current v0.3 inputs/outputs, inspect expected outcomes, then run through scan_runtime. |
| `runtime-assets.manifest.json` | Dated 2026-04-16 Windows asset inventory, old e8c282f base and external tools. It is not a current portable manifest. | Compare referenced roots with release payload and checksums; publish only regenerated non-machine-specific metadata. |
| `validation/config/`, `validation/templates/`, `validation/docker/` | Imported tool/runtime configuration and Docker recipe, no current environment validation in this frontend task. | Compare with root toolchain configuration and build context; run relevant container smoke on isolated data. |
| `plans/plc-adversarial-r2/experiment.json.lock` | Empty local process lock, not a deliverable. | Leave local; never stage runtime locks. |

The unresolved work exceeds frontend acceptance and lacks material/Windows/container evidence. This is a recoverable handoff, not a claim that those assets are useless. No runtime logs, sessions or environment secrets belong in new commits.
