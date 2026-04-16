#!/usr/bin/env bash
set -euo pipefail
cli_dir="${PLCVERIF_CLI_DIR:-/workspace/validation/tools/plcverif/cli}"
launcher="${cli_dir}/plugins/org.eclipse.equinox.launcher_1.4.0.v20161219-1356.jar"
exec java -jar "$launcher" "$@"
