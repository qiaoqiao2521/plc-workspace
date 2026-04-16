#!/usr/bin/env bash
set -euo pipefail

export WINEARCH="${WINEARCH:-win64}"
if [ ! -f "${WINEPREFIX:-/root/.wine}/system.reg" ] && command -v wineboot >/dev/null 2>&1; then
  wineboot --init >/tmp/nuxmv-wineboot.log 2>&1 || true
fi

target="${PLCVERIF_NUXMV_EXE:-/workspace/validation/tools/plcverif/tools/tools/nuxmv/nuXmv.exe}"
exec /usr/lib/wine/wine64 "$target" "$@"
