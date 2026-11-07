"""Exercise every implemented phase; GPU comparisons are opt-in and local only."""
import argparse
import json
from pathlib import Path
import uuid

from examples.advanced_samples import create_advanced
from design_editor.planner import plan
from design_editor.automation import run_trials
from design_editor.batch import execute_batch
from design_editor.generation import generate
from design_editor.multiview import validate_views, impact
from design_editor.benchmark import compare
from design_editor.learning import collect


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("runs"))
    parser.add_argument("--gpu", action="store_true")
    args = parser.parse_args()
    root = args.output / ("acceptance-" + uuid.uuid4().hex)
    fixtures = root / "fixtures"
    create_advanced(fixtures)
    catalog = json.loads((fixtures / "catalog.json").read_text())
    tasks = {}
    for index, instruction in enumerate(("表示灯の色だけ赤に変更", "make indicator square", "extract head")):
        request = plan(instruction, catalog, fixtures, root / ("plan-" + str(index)))
        _, report = run_trials(request, root)
        if report["status"] != "needs_visual_review":
            raise AssertionError("Phase 3 edit failed: " + instruction)
        tasks[instruction] = report["attempts"][-1]["report"]
    _, batch = execute_batch(json.loads((fixtures / "batch.json").read_text()), fixtures, root)
    assert batch["pass"]
    views = []
    for name in ("standard.json", "standard-alternative.json"):
        output, _ = generate(json.loads((fixtures / name).read_text()), root)
        check = json.loads((fixtures / "views-template.json").read_text())
        if name == "standard-alternative.json":
            for rule in check["visibility"]:
                rule["selector"]["rgb"] = [221, 51, 51]
        report = validate_views(check, output)
        assert report["pass"]
        views.append({"directory": output.name, "validation": report, "edit_impact": impact(check, "head", "front")})
    summary = {"tasks": tasks, "batch": batch, "views": views, "history_records": len(collect(root)["records"]), "gpu_comparison": "not requested", "visual_review": "required separately", "automatic_adoption": False}
    if args.gpu:
        request = json.loads((fixtures / "textile.json").read_text())
        for key in ("source", "editable_mask"):
            request[key] = str(fixtures / request[key])
        _, comparison = compare(request, json.loads((fixtures / "profiles.json").read_text()), root)
        assert all(r.get("report", {}).get("pixel_preservation_pass") for r in comparison["records"])
        summary["gpu_comparison"] = comparison
        # Impossible change threshold intentionally verifies bounded failure retention.
        request["quality"] = {"min_changed_pixels": 100000}
        policy = {"max_attempts": 2, "changes": [{"cause": "insufficient_change", "parameters": {"seed": 43}}]}
        _, retries = run_trials(request, root, policy)
        assert retries["status"] == "failed" and len(retries["attempts"]) == 2 and retries["best_candidate"]
        summary["expected_retry_failure"] = {"attempts": len(retries["attempts"]), "causes": [a["cause"] for a in retries["attempts"]], "best_candidate_saved": True}
    (root / "acceptance.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(root)


if __name__ == "__main__":
    main()
