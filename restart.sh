#!/bin/bash
set -euo pipefail
NAS_WIFI_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec /usr/bin/python3 "$NAS_WIFI_DIR/lib/manage.py" restart "$@"
