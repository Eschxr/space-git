#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
"${SPACEGIT_PYTHON:-.venv/bin/python}" scripts/doctor.py
