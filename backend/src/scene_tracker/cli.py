import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Scene Tracker developer CLI")
    parser.add_argument("command", choices=["worker"])
    parser.add_argument("queue", choices=["vision"])
    parser.add_argument("--burst", action="store_true", help="Exit when the queue is empty")
    args = parser.parse_args()
    from scene_tracker.workers.vision import work

    work(burst=args.burst)
