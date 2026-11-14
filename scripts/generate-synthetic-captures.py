"""Run with `cd backend && uv run python ../scripts/generate-synthetic-captures.py --output DIR`."""

import argparse
from pathlib import Path

from scene_tracker.vision.fixtures import generate_capture

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
generate_capture(args.output)
