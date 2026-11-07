"""Bounded, cause-specific trials; immutable source and permission boundary."""
import copy
import json
from pathlib import Path
import uuid

import requests

from .pipeline import run, digest


def classify(report):
    if not report.get("pixel_preservation_pass", False):
        return "protected_pixels_changed"
    if report.get("changed_pixels") == 0:
        return "no_change"
    if not report.get("expectations", {"pass": True})["pass"]:
        return "intent_constraints"
    if not report.get("quality", {"pass": True})["pass"]:
        kinds = {c["kind"] for c in report["quality"]["checks"] if not c["pass"]}
        return "shape_drift" if kinds & {"silhouette", "landmark", "symmetry", "edge_preservation"} else "insufficient_change"
    return "needs_visual_review"


ALLOWED = {"no_change": {"denoise", "seed", "prompt", "cfg"}, "insufficient_change": {"denoise", "seed", "prompt", "cfg"}, "intent_constraints": {"prompt", "seed", "cfg", "denoise"}, "shape_drift": {"denoise", "seed"}}


def run_trials(spec, root="runs", policy=None, backend=None):
    policy = policy or {"max_attempts": 1, "changes": []}
    maximum = policy.get("max_attempts", 1)
    if type(maximum) is not int or not 1 <= maximum <= 8:
        raise ValueError("max_attempts must be 1..8")
    for change in policy.get("changes", []):
        if not change["parameters"].keys() <= ALLOWED.get(change["cause"], set()):
            raise ValueError("Retry attempted to change parameters unrelated to its cause")
    directory = Path(root) / ("trials-" + uuid.uuid4().hex)
    directory.mkdir(parents=True, exist_ok=False)
    attempts, seen = [], set()
    current = copy.deepcopy(spec)
    source_hash = digest(spec["source"])
    fixed_hashes = {key: digest(spec[key]) for key in ("source", "editable_mask", "protected_mask", "reference_mask") if key in spec}
    best = None
    for index in range(maximum):
        signature = json.dumps(current, sort_keys=True)
        if signature in seen:
            break
        seen.add(signature)
        try:
            if digest(spec["source"]) != source_hash:
                raise ValueError("Source changed between attempts")
            if any(digest(spec[key]) != value for key, value in fixed_hashes.items()):
                raise ValueError("Source or permission masks changed between attempts")
            child, report = run(current, directory, backend)
            cause = classify(report)
            attempts.append({"directory": str(child.relative_to(directory)), "cause": cause, "report": report})
            # No-op candidates and preservation failures never outrank a valid changed edit.
            score = (report.get("pixel_preservation_pass", False), cause == "needs_visual_review", report.get("changed_pixels", 0) > 0)
            if best is None or score > best[0]:
                best = (score, child.name)
            if cause in ("needs_visual_review", "protected_pixels_changed"):
                break
            changes = [item for item in policy.get("changes", []) if item["cause"] == cause]
            if not changes or current["mode"] not in ("inpaint", "redesign"):
                break
            change = changes[min(index, len(changes) - 1)]["parameters"]
            if not change.keys() <= ALLOWED.get(cause, set()):
                raise ValueError("Retry attempted to change parameters unrelated to its cause")
            current.setdefault("parameters", {}).update(change)
        except (TimeoutError, ConnectionError, requests.RequestException) as error:
            attempts.append({"cause": "backend_unavailable_or_pending", "reason": str(error)})
            break  # never duplicate a job whose execution state is unknown
        except (ValueError, RuntimeError, KeyError) as error:
            attempts.append({"cause": "invalid_mask_request_or_backend_failure", "reason": str(error)})
            break
    summary = {"attempts": attempts, "best_candidate": best[1] if best else None, "accepted": False, "status": "needs_visual_review" if attempts and attempts[-1]["cause"] == "needs_visual_review" else "failed", "source_sha256": source_hash}
    (directory / "trials.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return directory, summary
