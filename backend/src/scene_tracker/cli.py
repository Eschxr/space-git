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
    readiness = commands.add_parser("model-readiness", help="Verify local assets; never downloads")
    readiness.add_argument("--runtime", action="store_true", help="Load real models/device too")
    smoke = commands.add_parser(
        "model-smoke", help="Manual real four-image inference; never downloads"
    )
    smoke.add_argument("--input", type=Path, required=True)
    smoke.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command in {"model-readiness", "model-smoke"}:
        import json

        from scene_tracker.core.errors import AppError
        from scene_tracker.core.settings import Settings
        from scene_tracker.vision.readiness import preflight

        settings = Settings()
        try:
            if args.command == "model-readiness":
                result = preflight(settings.vision)
                if args.runtime:
                    from scene_tracker.vision.runtime import load_models

                    *_, result = load_models(settings.vision)
                print(json.dumps(result, indent=2))
            else:
                from scene_tracker.vision.smoke import run_smoke

                print(json.dumps(run_smoke(args.input, args.output, settings), indent=2))
        except (AppError, ValueError) as exc:
            parser.exit(2, f"{getattr(exc, 'code', 'invalid_input')}: {exc}\n")
        return
    if args.command == "worker":
        from scene_tracker.workers.vision import work

        work(burst=args.burst)
    else:
        from scene_tracker.vision.fixtures import generate_capture

        generate_capture(args.output, empty=args.empty, moved=args.moved)
