#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOK_SOURCE="${REPO_ROOT}/.githooks/pre-commit"
HOOK_TARGET="${REPO_ROOT}/.git/hooks/pre-commit"

if [[ ! -d "${REPO_ROOT}/.git" ]]; then
  echo "No .git directory found at ${REPO_ROOT}."
  echo "Initialize git first, then rerun this script."
  exit 1
fi

if [[ ! -f "${HOOK_SOURCE}" ]]; then
  echo "Missing hook source: ${HOOK_SOURCE}"
  exit 1
fi

cp "${HOOK_SOURCE}" "${HOOK_TARGET}"
chmod +x "${HOOK_TARGET}"
echo "Installed pre-commit hook at ${HOOK_TARGET}"
