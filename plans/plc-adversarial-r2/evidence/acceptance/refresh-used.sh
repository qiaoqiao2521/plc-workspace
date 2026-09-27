#!/usr/bin/env bash
# Refresh the source-bound v0.3 evidence after a verification-scope change.
#
# Acceptance gates (2026-09-23 review P2): every positive layer must report an
# explicit pass, and the negative control must be REJECTED in this same run —
# gate exit 1 AND verdict "fail". Any other outcome aborts with exit 1 BEFORE
# anything is published. The staging directory is removed at the start, so every
# accepted artifact belongs to this run.
set -uo pipefail
REPO=/home/muqiao/repo-revival/plc-workspace
LAB=/home/muqiao/repo-revival/plc-adversarial-lab
IEC2C=$LAB/tools/bin/iec2c
MATLIB=$LAB/tools/matiec/lib
NUXMV=$LAB/tools/nuxmv/bin/nuXmv
PVCLI=$REPO/validation/tools/plcverif/cli
PROJ=$REPO/projects/FB_MainSequence
STAGE=/home/muqiao/repo-revival/plc-adversarial-r2/results/final-refresh-stage

fail() { echo "REFRESH FAILED: $*" >&2; exit 1; }
jsonfield() { python3 -c "import json,sys;print(json.load(open(sys.argv[1]))[sys.argv[2]])" "$1" "$2"; }

rm -rf "$STAGE"; mkdir -p "$STAGE"
cd "$REPO" || fail "cannot cd into repo"

echo "[1/7] sync --check"
python3 validation/scripts/sync-semantics.py --project "$PROJ" --check || fail "projection drift"

echo "[2/7] scan suite"
python3 validation/tests/test_scan_semantics.py --project "$PROJ" \
  --iec2c "$IEC2C" --matiec-lib "$MATLIB" --work-dir "$STAGE/scan-work" \
  > "$STAGE/scan-tests.log" 2>&1 || fail "scan suite exited nonzero"
cp "$STAGE/scan-work/result.json" "$STAGE/scan-result.json"
[ "$(jsonfield "$STAGE/scan-result.json" pass)" = "True" ] || fail "scan suite result is not pass"

echo "[3/7] native driver"
python3 validation/tests/run_openplc_driver.py --project "$PROJ" \
  --iec2c "$IEC2C" --matiec-lib "$MATLIB" --work-dir "$STAGE/driver-work" \
  > "$STAGE/native-driver.log" 2>&1 || fail "native driver exited nonzero"
cp "$STAGE/driver-work/result.json" "$STAGE/native-driver-result.json"
[ "$(jsonfield "$STAGE/native-driver-result.json" result)" = "pass" ] || fail "native driver result is not pass"

echo "[4/7] tooling suites"
python3 -m unittest discover -s validation/tests -p 'test_modelcheck_verdict.py' > "$STAGE/tooling-verdict.log" 2>&1 || fail "verdict suite failed"
python3 -m unittest discover -s validation/tests -p 'test_projection_sync.py' > "$STAGE/tooling-sync.log" 2>&1 || fail "projection suite failed"
python3 - "$STAGE" <<'PY' || fail "tooling suite log is not OK"
import json, re, sys
from pathlib import Path
stage = Path(sys.argv[1])
def count(p):
    t = p.read_text()
    return int(re.search(r"Ran (\d+) tests", t).group(1)), "OK" in t
vr, vp = count(stage/"tooling-verdict.log")
sr, sp = count(stage/"tooling-sync.log")
if not (vp and sp):
    sys.exit("tooling suite log is not OK")
(stage/"tooling-tests-result.json").write_text(json.dumps({
    "projection_tests": {"run": sr, "passed": sr},
    "verdict_tests": {"run": vr, "passed": vr},
    "evidence_kind": "results observed from unittest commands in this implementation turn",
}, indent=2) + "\n")
PY

echo "[5/7] formal gate (positive)"
set +e
python3 validation/scripts/run-semantic-modelcheck.py --project "$PROJ" \
  --plcverif-cli "$PVCLI" --backend "$NUXMV" --work-dir "$STAGE/formal" --timeout 300 \
  > "$STAGE/formal-gate.log"
formal_exit=$?
set -e
[ "$formal_exit" -eq 0 ] || fail "formal gate exit $formal_exit (must be 0)"
grep -q '"result": "pass"' "$STAGE/formal-gate.log" || fail "formal gate result is not pass"
latest=$(ls -d "$STAGE"/formal/2*/ | tail -1)
mkdir -p "$STAGE/formal-run"
cp -r "$latest" "$STAGE/formal-run/"

echo "[6/7] negative control (must be rejected)"
rm -rf "$STAGE/negative-project"
cp -a "$REPO/projects/FB_MainSequence" "$STAGE/negative-project"
cp "$REPO/projects/FB_MainSequence/03_checks/plcverif/assertions.scl" \
   "$STAGE/negative-project/03_checks/plcverif/assertions.scl"
cat >> "$STAGE/negative-project/03_checks/plcverif/assertions.scl" <<'NEG'
// Deliberately false negative control; must be rejected by the solver.
// Appended to the full required set (since the required-assertion gate refuses
// a replaced set, removal-weakening is rejected earlier by that gate, and this
// control keeps exercising the solver-rejects-a-false-requirement path).
//#ASSERT FALSE : NEGATIVE_CONTROL
NEG
python3 validation/scripts/sync-semantics.py --project "$STAGE/negative-project" --write >/dev/null \
  || fail "negative project sync failed"
set +e
python3 validation/scripts/run-semantic-modelcheck.py --project "$STAGE/negative-project" \
  --plcverif-cli "$PVCLI" --backend "$NUXMV" --work-dir "$STAGE/negative-formal" --timeout 300 \
  > "$STAGE/negative-gate.log"
neg_exit=$?
set -e
[ "$neg_exit" -eq 1 ] || fail "negative control gate exit $neg_exit (must be 1: rejected)"
negdir=$(ls -d "$STAGE"/negative-formal/2*/ | tail -1)
[ "$(jsonfield "$negdir/result.json" result)" = "fail" ] || fail "negative control verdict is not fail"
mkdir -p "$STAGE/negative-control"
cp -r "$negdir" "$STAGE/negative-control/"

echo "[7/7] all gates passed; publishing evidence"
python3 - "$REPO" "$STAGE" <<'PY' || fail "publication step failed"
import json, shutil, subprocess, sys
from pathlib import Path
repo, stage = Path(sys.argv[1]), Path(sys.argv[2])
proj = repo / "projects/FB_MainSequence"
evid = proj / "04_reports/semantics/v0.3"
compact = repo / "docs/verification/plc-semantics-v0.3"
gate = json.loads((stage / "formal-gate.log").read_text())
driver = json.loads((stage / "native-driver-result.json").read_text())
scan = json.loads((stage / "scan-result.json").read_text())
tooling = json.loads((stage / "tooling-tests-result.json").read_text())
tooling_total = tooling["projection_tests"]["run"] + tooling["verdict_tests"]["run"]
head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip()

shutil.rmtree(evid / "formal", ignore_errors=True)
shutil.copytree(stage / "formal-run", evid / "formal")
shutil.rmtree(evid / "negative-control", ignore_errors=True)
shutil.copytree(stage / "negative-control", evid / "negative-control")
for name in ("scan-tests.log", "scan-result.json", "native-driver.log",
             "native-driver-result.json", "tooling-tests-result.json",
             "formal-gate.log", "negative-gate.log"):
    shutil.copy2(stage / name, evid / name)
shutil.copy2(proj / "00_meta/projection-manifest.json", evid / "projection-manifest.json")

summary = {
    "status": "implemented_and_verified_abstract_core",
    "contract": "v0.3",
    "interface_version": "0.2.0",
    "base_head": head,
    "scan_tests": scan["tests_run"],
    "control_combinations": 160,
    "differential_calls": 5000,
    "tooling_tests": tooling_total,
    "formal_assertions": gate["assertion_count"],
    "formal_result": gate["result"],
    "formal_parameter_domain": gate["parameter_domain"],
    "formal_source_sha256": gate["source_sha256"],
    "formal_case_sha256": gate["case_sha256"],
    "projection_manifest_sha256": gate["projection_manifest_sha256"],
    "negative_control_gate_exit": 1,
    "adversarial_variant_pass": {
        "dates": "2026-09-22/23",
        "variants": 8,
        "system_level_misses_found": 2,
        "fixes": "P27-P31 (P29-P31 rewritten contract-derived after review) plus test_illegal_phase_reports_no_timeout; N=31 added to the native boundary samples",
        "equivalent_variants": 1,
        "detail": "see docs/DECISIONS.md and the plc-adversarial-lab report",
    },
    "migration": [
        "Maintain Enable; always invoke FB even while disabled",
        "Current block errors clear on an observed disabled call, not business Reset",
        "Enable rising clears historical timeout diagnostic",
        "Start/Reset edges are consumed even while rejected",
        "Five appended outputs and changed instance memory layout",
    ],
    "not_verified": [
        "TIA compilation/import and instance DB migration",
        "PLCSIM and real machine",
        "F safety implementation",
        "full OpenPLC service",
        "restart retention",
        "complete PLCopen conformance",
    ],
    "committed": False,
    "pushed": False,
}
(evid / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
(evid / "README.md").write_text(
f"""# Current source-bound evidence: scan contract v0.3

See summary.json for exact hashes and verification scope. formal/ contains the satisfied {gate['assertion_count']}-assertion conjunction; negative-control/ is the deliberately false rejected assertion (the refresh flow aborts unless the negative control is rejected with gate exit 1 and verdict fail). scan-tests.log includes {scan['tests_run']} compiled-ST tests (160 control combinations and 5,000 differential calls; boundary samples include threshold 31). native-driver-result.json covers the complete test program natively, not the OpenPLC service. P29-P31 are contract-derived deadline/count obligations revised after the 2026-09-23 independent review; see docs/DECISIONS.md. The prior parent-directory v0.2 results are historical.

Interface 0.2.0 changes command/error lifecycle and instance layout; see ../../../01_specs/scan-contract.md via the project specification directory. Current errors clear on an observed disabled call, diagnostics on the subsequent enable rise. TIA/PLCSIM/DB migration/retention/F safety remain separate and unverified.
""")
compact.mkdir(parents=True, exist_ok=True)
shutil.copy2(evid / "summary.json", compact / "summary.json")
shutil.copy2(stage / "formal-gate.log", compact / "formal-result.json")
report = list((stage / "formal-run").rglob("FB_MainSequence-assert-nusmv.report.txt"))[0]
shutil.copy2(report, compact / "formal-report.txt")
shutil.copy2(stage / "scan-tests.log", compact / "scan-tests.txt")
shutil.copy2(stage / "native-driver-result.json", compact / "native-driver-result.json")
shutil.copy2(stage / "tooling-tests-result.json", compact / "tooling-tests-result.json")
shutil.copy2(stage / "negative-gate.log", compact / "negative-control-result.json")
(compact / "README.md").write_text(
f"""# Compact verification records — plc-semantics v0.3

Summary hashes bind these results to the canonical-source projection and case. Scan tests: {scan['tests_run']}, including 160 control combinations and 5,000 differential calls (boundary samples include threshold 31); tooling tests: {tooling_total}; formal conjunction: {gate['assertion_count']} assertions satisfied. Native complete example: pass within the 801-call budget. The deliberately false assertion was rejected with gate exit 1 and verdict fail; the refresh flow enforces this as an acceptance condition. P29-P31 are contract-derived deadline/count obligations revised after the 2026-09-23 independent review. These are offline harness results, not Siemens or machine acceptance.
""")
print("published to", evid, "and", compact)
PY
echo "refresh complete: all acceptance gates passed and evidence published"
