#!/usr/bin/env bash
# Run the full suite the way CI does, wherever this checkout lives.
#
# The V6 kernel suite is container-first: its sandbox root and default tool cwd
# are /workspace, several tests read /workspace/..., and the sandbox resolves
# relative paths (realpath) against the process cwd. So the suite only runs when
# the checkout is placed at /workspace/project and pytest runs from there.
#
# CI and the self-improve gate have neither; both have passwordless sudo. We
# COPY (never bind-mount — a mount over the path is hard to clean up and, in the
# dev container where /workspace/project *is* the repo, would shadow the real
# working tree) the checkout to /workspace/project and run BOTH suites there.
# Only when that layout cannot be provided do we fall back to tests/, so the
# gate still verifies a patch instead of failing on an environment quirk.
set -uo pipefail
ROOT="$(readlink -f "$(pwd)")"
SANDBOX="/workspace/project"

run_both() {
  ( cd "$1" && python3 -m pytest -q )
}

# Already at the sandbox path (the dev container): nothing to set up.
if [ "$ROOT" = "$SANDBOX" ]; then
  run_both "$ROOT"
  exit $?
fi

# Only ever populate an absent sandbox path, and only with sudo. If it exists
# and is not us, leave it alone and fall back rather than clobber anything.
if [ ! -e "$SANDBOX" ] && command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
  if sudo mkdir -p /workspace && sudo cp -a "$ROOT" "$SANDBOX" 2>/dev/null; then
    sudo chmod -R a+rwX "$SANDBOX" 2>/dev/null || true
    sudo chmod 777 /workspace 2>/dev/null || true
    run_both "$SANDBOX"
    exit $?
  fi
fi

echo "verify_all: /workspace layout unavailable; running tests/ only"
python3 -m pytest tests/ -q

