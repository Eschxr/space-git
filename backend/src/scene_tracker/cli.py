import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Scene Tracker developer CLI")
    parser.add_argument("command", choices=["worker"])
    parser.add_argument("queue", choices=["vision"])
    parser.parse_args()
    parser.exit(2, "Vision worker is not implemented until Phase 2; no inference ran.\n")
