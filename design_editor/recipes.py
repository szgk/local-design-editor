"""Explicit reuse of hash-verified, reviewed runs; no automatic algorithm updates."""
import copy
import json
import hashlib
from pathlib import Path

from .pipeline import digest


def fingerprint(spec, artifacts=None):
    fixed = {key: spec[key] for key in ("mode", "instruction", "hue", "geometry", "box", "feather", "expectations", "quality") if key in spec}
    for key, name in (("editable_mask", "editable.png"), ("protected_mask", "protected.png"), ("reference_mask", "reference.png")):
        if key in spec:
            fixed[key] = digest(Path(artifacts) / name if artifacts else spec[key])
    return hashlib.sha256(json.dumps(fixed, sort_keys=True).encode()).hexdigest()


def verified_recipe(run_directory):
    directory = Path(run_directory)
    report = json.loads((directory / "validation.json").read_text(encoding="utf-8"))
    result_hash = digest(directory / "result.png")
    if result_hash != report["result_sha256"] or report["overall_status"] == "failed" or not report["pixel_preservation_pass"] or not report["source_unchanged"]:
        raise ValueError("Cannot reuse a failed or modified run")
    reviews = [json.loads(p.read_text(encoding="utf-8")) for p in directory.glob("review-*.json")]
    reviews = [r for r in reviews if r["result_sha256"] == result_hash and r["validation_sha256"] == digest(directory / "validation.json")]
    if not any(r["status"] == "accepted" for r in reviews) or any(r["status"] == "rejected" for r in reviews):
        raise ValueError("A valid uncontradicted acceptance review is required")
    spec = json.loads((directory / "request.json").read_text(encoding="utf-8"))
    return {"schema": 1, "source_sha256": report["source_sha256"], "result_sha256": result_hash, "request_fingerprint": fingerprint(spec, directory), "mode": spec["mode"], "parameters": copy.deepcopy(spec.get("parameters", {})), "automatic_adoption": False}


def apply_recipe(spec, recipe):
    if recipe.get("schema") != 1 or digest(spec["source"]) != recipe["source_sha256"] or spec["mode"] != recipe["mode"] or fingerprint(spec) != recipe["request_fingerprint"]:
        raise ValueError("Recipe input or operation differs from the reviewed evidence")
    result = copy.deepcopy(spec)
    result["parameters"] = copy.deepcopy(recipe["parameters"])
    result["recipe_evidence"] = recipe["result_sha256"]
    return result
