"""Worker entry point and local command for Open3D surface reconstruction."""

import argparse
import json
import shutil
import sys
from pathlib import Path

from surface_pipeline import Settings, process_view


def run_job(config):
    output = Path(config['output'])
    base = Path(config['base']) if config.get('base') else None
    reports = {}
    for slot, source in config['sources'].items():
        def stage(message):
            print(json.dumps({'stage': message, 'slot': int(slot), 'completed': len(reports)}), flush=True)

        reports[slot] = process_view(
            Path(source), output/slot, Settings(**config['settings']), stage,
            camera_origin=config.get('camera_origin', False), base=base/slot if base else None,
            analysis_only=config.get('analysis_only', False),
        )
    (output/'report.json').write_text(json.dumps(reports, indent=2), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, nargs='?')
    parser.add_argument('output', type=Path, nargs='?')
    parser.add_argument('--depth', type=int, choices=range(5, 12), default=9)
    parser.add_argument('--smoothing', type=int, choices=range(16), default=3)
    parser.add_argument('--job', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        if args.job:
            run_job(json.loads(args.job.read_text(encoding='utf-8')))
        elif args.source and args.output:
            args.output.mkdir(parents=True, exist_ok=False)
            process_view(args.source, args.output, Settings(depth=args.depth, smoothing=args.smoothing),
                         print)
            shutil.copyfile(args.source, args.output/'original.ply')
        else:
            parser.error('Supply an input PLY and a new output directory.')
    except (ValueError, OSError, RuntimeError) as error:
        print(json.dumps({'error': str(error)}), file=sys.stderr, flush=True)
        return 1
    return 0


if __name__=='__main__':
    sys.exit(main())
