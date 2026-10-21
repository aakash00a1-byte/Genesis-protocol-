#!/usr/bin/env bash
# Deploy the current repository state to the Hugging Face Space git repo.
#
# Why this exists: the HF Space (GenesisNo/Genesis-Automaton) is a STANDALONE
# git repo, not linked to GitHub. A `git push` to GitHub does NOT update the
# Space. This script mirrors the repo into the Space repo and pushes, so the
# Space rebuilds with the current code.
#
# Usage:
#   HF_TOKEN=hf_xxxxxxxx bash scripts/hf_deploy.sh
#
# Env overrides:
#   HF_SPACE_REPO   Space id (default: GenesisNo/Genesis-Automaton)
#   HF_USERNAME     Basic-auth username (default: hf); the token is the password
#   SRC_DIR         Source repo root (default: this script's parent dir)
set -euo pipefail

: "${HF_TOKEN:?Set HF_TOKEN to a Hugging Face WRITE token (https://huggingface.co/settings/tokens)}"
SPACE="${HF_SPACE_REPO:-GenesisNo/Genesis-Automaton}"
HF_USERNAME="${HF_USERNAME:-hf}"
SRC="${SRC_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

EXCLUDES=(
  '.git' '.env' '.venv' 'venv' '__pycache__' '*.pyc' '*.db'
  'node_modules' '.agents' '.openhands' '.pytest_cache' '.ruff_cache'
  '.agent_tmp' '.mypy_cache' 'workspace'
)

echo "[1/5] Cloning Space ${SPACE} ..."
git clone --quiet "https://${HF_USERNAME}:${HF_TOKEN}@huggingface.co/spaces/${SPACE}" "$WORK/space"

echo "[2/5] Preserving Space metadata (README front-matter, .gitattributes) ..."
cp "$WORK/space/README.md" "$WORK/README.space.md"
if [ -f "$WORK/space/.gitattributes" ]; then
  cp "$WORK/space/.gitattributes" "$WORK/gitattributes.space"
fi

echo "[3/5] Mirroring repository into Space ..."
tar_args=()
for e in "${EXCLUDES[@]}"; do tar_args+=(--exclude="$e"); done
( cd "$SRC" && tar "${tar_args[@]}" -cf - . ) | ( cd "$WORK/space" && tar -xf - )

echo "[4/5] Restoring Space README/.gitattributes and HF Dockerfile ..."
cp "$WORK/README.space.md" "$WORK/space/README.md"
[ -f "$WORK/gitattributes.space" ] && cp "$WORK/gitattributes.space" "$WORK/space/.gitattributes"
cp "$WORK/space/Dockerfile.hf" "$WORK/space/Dockerfile"

echo "[5/5] Committing and pushing ..."
cd "$WORK/space"
git add -A
if git diff --cached --quiet; then
  echo "Nothing to deploy (Space already matches this repo)."
  exit 0
fi
SHA="$(cd "$SRC" && git rev-parse --short HEAD 2>/dev/null || echo unknown)"
git -c user.name="genesis-deploy" -c user.email="deploy@genesis.local" \
  commit -q -m "deploy: sync from GitHub main (${SHA})"
git push --quiet origin HEAD:main
echo "Deployed ${SHA}. The HF Space will rebuild automatically."
