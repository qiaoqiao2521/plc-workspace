#!/usr/bin/env bash
set -euo pipefail

export WINEARCH="${WINEARCH:-win64}"
if [ ! -f "${WINEPREFIX:-/root/.wine}/system.reg" ] && command -v wineboot >/dev/null 2>&1; then
  wineboot --init >/tmp/iec-checker-wineboot.log 2>&1 || true
fi

target="${IEC_CHECKER_WINDOWS_EXE:-/workspace/validation/tools/iec-checker/iec_checker_Windows_x86_64.exe}"
exec /usr/lib/wine/wine64 "$target" "$@"
