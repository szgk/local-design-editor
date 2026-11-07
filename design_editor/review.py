"""Append-only visual assessment, bound to the actual reviewed result hash."""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .pipeline import digest


def record_review(directory, status, reviewer, note, result_sha256):
    directory = Path(directory)
    report = json.loads((directory / "validation.json").read_text(encoding="utf-8"))
    actual = digest(directory / "result.png")
    if actual != result_sha256 or actual != report["result_sha256"]:
        raise ValueError("Result hash differs from the reviewed or validated artifact")
    if status not in ("accepted", "rejected") or not reviewer.strip() or not note.strip():
        raise ValueError("Provide a review status, reviewer and concrete visual assessment")
    if status == "accepted" and (not report["pixel_preservation_pass"] or not report["source_unchanged"] or not report.get("expectations", {"pass": True})["pass"] or (report.get("changed_pixels") == 0)):
        raise ValueError("Cannot accept failed constraints or an unchanged edit")
    record = {"status": status, "reviewer": reviewer, "note": note, "result_sha256": actual, "validation_sha256": digest(directory / "validation.json"), "created_at": datetime.now(timezone.utc).isoformat()}
    path = directory / ("review-" + uuid.uuid4().hex + ".json")
    with path.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2)
    return path
