#!/usr/bin/env bash
set -euo pipefail

target="${IEC_CHECKER_BIN:-/opt/iec-checker/iec_checker}"
exec "$target" "$@"
