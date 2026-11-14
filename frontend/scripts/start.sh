#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export SPACEGIT_MODE="${1:-demo}"
export SPACEGIT_LOCAL_SESSION=1
case "$SPACEGIT_MODE" in demo|live) ;; *) echo "Use demo or live" >&2; exit 2;; esac
sg_python="${SPACEGIT_PYTHON:-.venv/bin/python}"
test -x "$sg_python" || { echo "Set up the Python virtual environment first; see README." >&2; exit 1; }
export NEXT_TELEMETRY_DISABLED=1
export SPACEGIT_TOKEN="${SPACEGIT_TOKEN:-$("$sg_python" -c 'import secrets;print(secrets.token_urlsafe(32))')}"
"$sg_python" -m uvicorn spacegit_edge.main:app --app-dir apps/edge --host 127.0.0.1 --port 8000 --no-access-log --ws-max-size 1024 &
sg_edge=$!
trap 'kill "$sg_edge" 2>/dev/null || true; wait "$sg_edge" 2>/dev/null || true' EXIT
sg_ready=
for i in {1..30}; do
  kill -0 "$sg_edge" 2>/dev/null || break
  if "$sg_python" -c 'import os,json,urllib.request; r=urllib.request.urlopen("http://127.0.0.1:8000/health",timeout=1); assert json.load(r)["mode"]==os.environ["SPACEGIT_MODE"]' 2>/dev/null; then sg_ready=1; break; fi
  sleep .25
done
test -n "$sg_ready" || { echo "Edge did not start; check dependencies and port 8000." >&2; exit 1; }
printf 'SpaceGit %s · http://127.0.0.1:3000/setup\nLocal operator key (paste in Setup): %s\n' "$SPACEGIT_MODE" "$SPACEGIT_TOKEN"
pnpm dev
