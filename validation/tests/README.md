# Semantic verification

These checks validate the abstract FB, not Siemens engineering integration. Python 3.10+, GCC and the bundled matiec compiler are required for compiled-ST tests. Tested on Linux.

From the repository root:

```bash
python3 validation/scripts/sync-semantics.py --project projects/FB_MainSequence --check
python3 validation/tests/test_scan_semantics.py \
  --project projects/FB_MainSequence \
  --iec2c /absolute/path/to/matiec/iec2c \
  --matiec-lib /absolute/path/to/matiec/lib \
  --work-dir /absolute/path/to/test-output
python3 -m unittest discover -s validation/tests -p 'test_modelcheck_verdict.py' -v
python3 -m unittest discover -s validation/tests -p 'test_projection_sync.py' -v
```

After changing authoritative ST, assertion comments, driver or contract, regenerate with `sync-semantics.py --write` before checking. The generator refuses an unexpected source-unit set; add dependencies explicitly rather than guessing order.

matIEC can be built from a scratch copy of `validation/tools/OpenPLC_v3/utils/matiec_src` using `autoreconf -i`, `./configure`, and `make`. Historical release text may require CRLF normalization in that scratch copy. Do not rewrite vendor sources in the working tree merely to run tests.

The runner builds three small native libraries from the canonical ST and derived checker dialects. Its tests include cutoff scans, completion at the cutoff, live parameter reduction, zero timeout, UINT boundaries, illegal states, Done behavior and 5,000 deterministic differential invocations. State injection is test-only.

Formal entry point:

```bash
python3 validation/scripts/run-semantic-modelcheck.py \
  --project projects/FB_MainSequence \
  --plcverif-cli /absolute/path/to/isolated/plcverif/cli \
  --backend /absolute/path/to/nuXmv \
  --work-dir /absolute/path/to/formal-output
```

This runs one generated source/case in a fresh directory, checks projection hashes first, and returns 0 only for an unambiguous satisfied result. Violated returns 1; unknown/tool error/timeout returns 2. Keep the generated model and log together with result.json. The parameter domain and implemented contract scope must be reported honestly.

Existing full static/OpenPLC/TIA gates are separate acceptance layers. Their missing dependencies or evidence are not repaired by passing these semantic tests.

## Continuous-enable contract v0.3

The scan suite has 27 tests, including 160 simultaneous-control combinations, edge consumption, current-error/diagnostic lifetime, output poisoning and 5,000 differential calls. The final formal case has 32 assertions. The complete generated OpenPLC example can also run natively:

```bash
python3 validation/tests/run_openplc_driver.py \
  --project projects/FB_MainSequence \
  --iec2c /absolute/path/to/matiec/iec2c \
  --matiec-lib /absolute/path/to/matiec/lib \
  --work-dir /absolute/path/to/native-driver-output
```

This executes the generated test program and located monitor flags for at most 801 calls, returning nonzero on failure/unknown. It does not start an OpenPLC service. The driver's timeout recovery now performs an observed disabled call; business Reset no longer clears block errors.

The required-assertions.txt baseline pins full assertion expressions and must be nonempty. Additional FALSE assertions remain available for negative controls. On slower hosts the 60-second default may return UNKNOWN; an explicit --timeout 300 diagnostic run does not change verdict semantics. Current evidence records the budget used.
