#!/usr/bin/env bash
set -euo pipefail

target="${PLCVERIF_NUXMV_BIN:-/opt/nuxmv/bin/nuXmv}"
exec "$target" "$@"
