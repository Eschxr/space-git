import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Scene Tracker developer CLI")
    commands = parser.add_subparsers(dest="command", required=True)
    worker = commands.add_parser("worker")
    worker.add_argument("queue", choices=["vision"])
    worker.add_argument("--burst", action="store_true")
    synthetic = commands.add_parser("synthetic-capture", help="Generate four labeled fake PNGs")
    synthetic.add_argument("--output", type=Path, required=True)
    synthetic.add_argument("--empty", action="store_true")
    synthetic.add_argument("--moved", action="store_true")
    args = parser.parse_args()
    if args.command == "worker":
        from scene_tracker.workers.vision import work

        work(burst=args.burst)
    else:
        from scene_tracker.vision.fixtures import generate_capture

        generate_capture(args.output, empty=args.empty, moved=args.moved)
