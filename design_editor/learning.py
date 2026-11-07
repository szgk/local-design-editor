"""Searchable evidence summaries. Observations never become executable defaults."""
import json
from pathlib import Path


def collect(root):
    records = []
    for path in Path(root).rglob("validation.json"):
        report = json.loads(path.read_text(encoding="utf-8"))
        reviews = [json.loads(p.read_text(encoding="utf-8")) for p in path.parent.glob("review-*.json")]
        records.append({"source_sha256": report.get("source_sha256"), "result_sha256": report.get("result_sha256"), "pixel_preservation_pass": report.get("pixel_preservation_pass"), "overall_status": report.get("overall_status"), "review_statuses": [r["status"] for r in reviews if r["result_sha256"] == report.get("result_sha256")], "automatic_adoption": False})
    for path in Path(root).rglob("generation.json"):
        report = json.loads(path.read_text(encoding="utf-8"))
        reviews = [json.loads(p.read_text(encoding="utf-8")) for p in path.parent.glob("review-*.json")]
        records.append({"operation": "new_generation", "result_hashes": report["result_hashes"], "review_statuses": [r["status"] for r in reviews if r.get("result_sha256") == report.get("sheet_sha256")], "automatic_adoption": False})
    for path in Path(root).rglob("failure.json"):
        report = json.loads(path.read_text(encoding="utf-8"))
        records.append({"overall_status": "failed", "failure_type": report.get("type"), "automatic_adoption": False})
    return {"records": records, "observations_only": True, "default_updates": False}
