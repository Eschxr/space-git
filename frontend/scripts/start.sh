#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export SPACEGIT_MODE="${1:-demo}"
export SPACEGIT_LOCAL_SESSION=1
case "$SPACEGIT_MODE" in demo|live) ;; *) echo "Use demo or live" >&2; exit 2;; esac
sg_python="${SPACEGIT_PYTHON:-.venv/bin/python}"
sg_web_port="${SPACEGIT_WEB_PORT:-3000}"
sg_edge_port="${SPACEGIT_EDGE_PORT:-8000}"
for sg_port in "$sg_web_port" "$sg_edge_port"; do
  [[ "$sg_port" =~ ^[0-9]{4,5}$ ]] && (( 10#$sg_port >= 1024 && 10#$sg_port <= 65535 )) || { echo "Ports must be between 1024 and 65535" >&2; exit 2; }
done
test -x "$sg_python" || { echo "Set up the Python virtual environment first; see README." >&2; exit 1; }
export NEXT_TELEMETRY_DISABLED=1
export NEXT_PUBLIC_SPACEGIT_EDGE_URL="http://127.0.0.1:$sg_edge_port"
export SPACEGIT_EDGE_PORT="$sg_edge_port"
export SPACEGIT_EDGE_HEALTH="$NEXT_PUBLIC_SPACEGIT_EDGE_URL/health"
export SPACEGIT_TOKEN="${SPACEGIT_TOKEN:-$("$sg_python" -c 'import secrets;print(secrets.token_urlsafe(32))')}"
"$sg_python" -m uvicorn spacegit_edge.main:app --app-dir apps/edge --host 127.0.0.1 --port "$sg_edge_port" --no-access-log --ws-max-size 1024 &
sg_edge=$!
trap 'kill "$sg_edge" 2>/dev/null || true; wait "$sg_edge" 2>/dev/null || true' EXIT
sg_ready=
for i in {1..30}; do
  kill -0 "$sg_edge" 2>/dev/null || break
  if "$sg_python" -c 'import os,json,urllib.request; r=urllib.request.urlopen(os.environ["SPACEGIT_EDGE_HEALTH"],timeout=1); assert json.load(r)["mode"]==os.environ["SPACEGIT_MODE"]' 2>/dev/null; then sg_ready=1; break; fi
  sleep .25
done
test -n "$sg_ready" || { echo "Edge did not start; check dependencies and port $sg_edge_port." >&2; exit 1; }
printf 'SpaceGit %s · http://127.0.0.1:%s/setup\nLocal operator key (paste in Setup): %s\n' "$SPACEGIT_MODE" "$sg_web_port" "$SPACEGIT_TOKEN"
pnpm dev --port "$sg_web_port"
