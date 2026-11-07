import argparse
import json
from pathlib import Path

from .imaging import load, make_mask
from .pipeline import run


def read_request(path):
    spec = json.loads(path.read_text(encoding="utf-8"))
    for key in ("source", "candidate", "editable_mask", "protected_mask", "reference_mask"):
        if key in spec:
            spec[key] = str((path.parent / spec[key]).resolve())
    return spec


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
    auto = commands.add_parser("auto", help="Interpret a supported edit instruction using an explicit target catalog")
    auto.add_argument("catalog", type=Path)
    auto.add_argument("instruction")
    auto.add_argument("--output", default="runs")
    auto.add_argument("--plan-only", action="store_true")
    trials = commands.add_parser("trials", help="Bounded cause-specific retries")
    trials.add_argument("request", type=Path)
    trials.add_argument("policy", type=Path)
    trials.add_argument("--output", default="runs")
    compare = commands.add_parser("compare", help="Same-condition local model comparison")
    compare.add_argument("request", type=Path)
    compare.add_argument("profiles", type=Path)
    compare.add_argument("--output", default="runs")
    views = commands.add_parser("views", help="Measure declared cross-view landmarks")
    views.add_argument("spec", type=Path)
    views.add_argument("--output", type=Path, required=True)
    views.add_argument("--feature")
    views.add_argument("--edited-view", default="front")
    batch = commands.add_parser("batch")
    batch.add_argument("spec", type=Path)
    batch.add_argument("--output", default="runs")
    generation = commands.add_parser("generate", help="New designs; never an existing-image edit")
    generation.add_argument("spec", type=Path)
    generation.add_argument("--output", default="runs")
    learn = commands.add_parser("history", help="Collect observations without changing defaults")
    learn.add_argument("root", type=Path)
    learn.add_argument("--output", type=Path, required=True)
    recipe = commands.add_parser("recipe", help="Export an explicitly reviewed parameter recipe")
    recipe.add_argument("run", type=Path)
    recipe.add_argument("output", type=Path)
    reuse = commands.add_parser("reuse", help="Apply a recipe only to the same source and mode")
    reuse.add_argument("request", type=Path)
    reuse.add_argument("recipe", type=Path)
    reuse.add_argument("--output", default="runs")
    args = parser.parse_args()
    if args.command == "mask":
        if args.output.exists():
            parser.error("Mask output already exists; choose a new filename")
        regions = json.loads(args.regions.read_text(encoding="utf-8"))
        make_mask(load(args.source).size, **regions).save(args.output)
    elif args.command == "review":
        from .review import record_review
        print(record_review(args.directory, args.status, args.reviewer, args.note, args.result_sha256))
    elif args.command == "auto":
        import uuid
        from .planner import plan
        from .automation import run_trials
        catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
        directory = Path(args.output) / ("plan-" + uuid.uuid4().hex)
        spec = plan(args.instruction, catalog, args.catalog.parent, directory)
        (directory / "request.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
        if args.plan_only:
            print(directory)
        else:
            child, report = run_trials(spec, args.output)
            print(json.dumps({"directory": str(child), **report}, indent=2))
            if report["status"] == "failed":
                raise SystemExit(2)
    elif args.command in ("trials", "compare"):
        if args.command == "trials":
            from .automation import run_trials
            directory, report = run_trials(read_request(args.request), args.output, json.loads(args.policy.read_text(encoding="utf-8")))
        else:
            from .benchmark import compare
            directory, report = compare(read_request(args.request), json.loads(args.profiles.read_text(encoding="utf-8")), args.output)
        print(json.dumps({"directory": str(directory), **report}, indent=2))
        if report.get("status") == "failed" or any(r["status"] == "failed" for r in report.get("records", [])):
            raise SystemExit(2)
    elif args.command == "views":
        from .multiview import validate_views, impact
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
        report = validate_views(spec, args.spec.parent)
        if args.feature:
            report["impact"] = impact(spec, args.feature, args.edited_view)
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
        print(json.dumps(report, indent=2))
        if not report["pass"]:
            raise SystemExit(2)
    elif args.command in ("batch", "generate"):
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
        if args.command == "batch":
            from .batch import execute_batch
            directory, report = execute_batch(spec, args.spec.parent, args.output)
        else:
            from .generation import generate
            directory, report = generate(spec, args.output)
        print(json.dumps({"directory": str(directory), **report}, indent=2))
        if report.get("pass") is False:
            raise SystemExit(2)
    elif args.command == "history":
        from .learning import collect
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(collect(args.root), stream, indent=2)
    elif args.command == "recipe":
        from .recipes import verified_recipe
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(verified_recipe(args.run), stream, indent=2)
    elif args.command == "reuse":
        from .recipes import apply_recipe
        spec = apply_recipe(read_request(args.request), json.loads(args.recipe.read_text(encoding="utf-8")))
        directory, report = run(spec, args.output)
        print(json.dumps({"directory": str(directory), **report}, indent=2))
        if report["overall_status"] == "failed":
            raise SystemExit(2)
    else:
        spec = read_request(args.request)
        directory, report = run(spec, args.output)
        print(json.dumps({"directory": str(directory), **report}, indent=2))
        if not report["pixel_preservation_pass"] or report["overall_status"] == "failed":
            raise SystemExit(2)


if __name__ == "__main__":
    main()
