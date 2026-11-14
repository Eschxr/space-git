import argparse


def main() -> None:
    parser = argparse.ArgumentParser(description="Isolated per-view reconstruction worker")
    parser.parse_args()
    parser.exit(2, "PointDiT worker is not implemented until Phase 9; no inference ran.\n")
