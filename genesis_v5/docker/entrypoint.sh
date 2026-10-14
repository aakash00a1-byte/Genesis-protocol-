#!/bin/sh
# Genesis V5 container entrypoint — development, testing, or production via
# GENESIS_ENV. Never requires credentials; adapters stay DISABLED unless
# configured at runtime.

set -eu

echo "genesis-v5 starting (env=${GENESIS_ENV:-production}, offline=${GENESIS_OFFLINE:-true})"

case "${1:-serve}" in
  serve|web)
    # Placeholder server invocation; replace with the real web/API entrypoint
    # (e.g. uvicorn) when a server layer is added.
    python - <<'PY'
import json, sys, time
while True:
    msg = {"app": "genesis-v5", "status": "ok", "ts": time.time()}
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()
    time.sleep(30)
PY
    ;;
  check)
    python - <<'PY'
from genesis.bootstrap import build
k = build()
print("kernel-health:", "ok" if k.health() else "unhealthy")
PY
    ;;
  *)
    exec "$@"
    ;;
esac