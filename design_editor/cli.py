import argparse
import json
from pathlib import Path

from .imaging import load, make_mask
from .pipeline import run


def main():
    parser = argparse.ArgumentParser(description="Local design editor: preserve unspecified pixels")
    commands = parser.add_subparsers(dest="command", required=True)
    edit = commands.add_parser("run")
    edit.add_argument("request", type=Path)
    edit.add_argument("--output", default="runs")
    mask = commands.add_parser("mask")
    mask.add_argument("source")
    mask.add_argument("regions", type=Path, help="JSON with boxes and/or polygons")
    mask.add_argument("output", type=Path)
    review = commands.add_parser("review", help="Record a visual assessment of a specific result; never auto-approve")
    review.add_argument("directory", type=Path)
    review.add_argument("--status", choices=("accepted", "rejected"), required=True)
    review.add_argument("--reviewer", required=True)
    review.add_argument("--note", required=True)
    review.add_argument("--result-sha256", required=True)
    args = parser.parse_args()
    if args.command == "mask":
        if args.output.exists():
            parser.error("Mask output already exists; choose a new filename")
        regions = json.loads(args.regions.read_text(encoding="utf-8"))
        make_mask(load(args.source).size, **regions).save(args.output)
    elif args.command == "review":
        from .review import record_review
        print(record_review(args.directory, args.status, args.reviewer, args.note, args.result_sha256))
    else:
        spec = json.loads(args.request.read_text(encoding="utf-8"))
        # All asset paths in a request are relative to that request, not the shell cwd.
        for key in ("source", "candidate", "editable_mask", "protected_mask", "reference_mask"):
            if key in spec:
                spec[key] = str((args.request.parent / spec[key]).resolve())
        directory, report = run(spec, args.output)
        print(json.dumps({"directory": str(directory), **report}, indent=2))
        if not report["pixel_preservation_pass"] or report["overall_status"] == "failed":
            raise SystemExit(2)


if __name__ == "__main__":
    main()
