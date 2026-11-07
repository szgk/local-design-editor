"""Run the same explicit edit across registered designs, retaining per-input evidence."""
import json
from pathlib import Path
import uuid

from .planner import plan
from .automation import run_trials


def execute_batch(spec, base, root="runs", backend=None):
    directory = Path(root) / ("batch-" + uuid.uuid4().hex)
    directory.mkdir(parents=True, exist_ok=False)
    results = []
    for index, item in enumerate(spec["items"]):
        path = Path(base) / item["catalog"]
        try:
            catalog = json.loads(path.read_text(encoding="utf-8"))
            request = plan(item.get("instruction", spec.get("instruction", "")), catalog, path.parent, directory / ("plan-" + str(index)))
            child, report = run_trials(request, directory, item.get("retry", spec.get("retry")), backend)
            results.append({"item": index, "directory": child.name, "status": report["status"]})
        except (ValueError, KeyError, OSError) as error:
            results.append({"item": index, "status": "failed", "reason": str(error)})
    summary = {"results": results, "automatic_adoption": False, "pass": bool(results) and all(r["status"] == "needs_visual_review" for r in results)}
    (directory / "batch.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return directory, summary
