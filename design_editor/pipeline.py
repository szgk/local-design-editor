import hashlib
import json
import shutil
import time
import uuid
from pathlib import Path

import numpy as np
from PIL import Image

from .imaging import load, mask_load, effective_mask, composite, recolor, crop
from .validation import verify


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(spec, root="runs", backend=None):
    directory = Path(root) / uuid.uuid4().hex
    directory.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    (directory / "request.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
    try:
        source = Path(spec["source"])
        source_hash = digest(source)
        shutil.copyfile(source, directory / ("source" + source.suffix))
        original = load(source)
        mode = spec["mode"]
        if mode == "extract":
            extracted = original.copy()
            if spec.get("editable_mask"):
                alpha_mask = mask_load(spec["editable_mask"], original.size)
                Image.fromarray(alpha_mask).save(directory / "editable.png")
                pixels = np.array(extracted)
                pixels[..., 3] = np.minimum(pixels[..., 3], alpha_mask)
                extracted = Image.fromarray(pixels)
            result = crop(extracted, spec["box"])
            report = {"pixel_preservation_pass": True, "operation": "masked_crop" if spec.get("editable_mask") else "exact_crop", "box": spec["box"], "intent_review": "pending", "overall_status": "needs_visual_review"}
        else:
            editable = mask_load(spec["editable_mask"], original.size)
            protected = mask_load(spec["protected_mask"], original.size) if spec.get("protected_mask") else None
            if spec.get("reference_mask"):
                Image.fromarray(mask_load(spec["reference_mask"], original.size)).save(directory / "reference.png")
            Image.fromarray(editable).save(directory / "editable.png")
            if protected is not None:
                Image.fromarray(protected).save(directory / "protected.png")
            effective = effective_mask(editable, protected, spec.get("feather", 0))
            Image.fromarray(effective).save(directory / "effective.png")
            if mode == "recolor":
                candidate = recolor(original, spec["hue"])
            elif mode == "composite":
                candidate = load(spec["candidate"])
            elif mode in ("inpaint", "redesign"):
                if backend is None:
                    from .comfy import ComfyBackend
                    backend = ComfyBackend(spec.get("url", "http://127.0.0.1:8188"), spec.get("timeout", 300))
                candidate = backend.generate(original, Image.fromarray(effective), spec["parameters"], directory)
            else:
                raise ValueError("Supported modes: extract, recolor, composite, inpaint, redesign")
            candidate.save(directory / "candidate.png")
            result = composite(original, candidate, effective)
            report, heat = verify(original, result, editable, protected)
            heat.save(directory / "difference.png")
            comparison = Image.new("RGBA", (original.width * 3, original.height))
            for i, image in enumerate((original, result, heat)):
                comparison.paste(image, (i * original.width, 0))
            comparison.save(directory / "comparison.png")
        result.save(directory / "result.png")
        report.update(source_sha256=source_hash, source_unchanged=digest(source) == source_hash, result_sha256=digest(directory / "result.png"), elapsed_seconds=time.monotonic() - started)
        if not report["source_unchanged"]:
            raise RuntimeError("Source file changed during execution")
        (directory / "validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        (directory / "events.jsonl").write_text(json.dumps({"event": "completed", "status": report["overall_status"]}) + "\n", encoding="utf-8")
        return directory, report
    except Exception as error:
        (directory / "failure.json").write_text(json.dumps({"status": "failed", "type": type(error).__name__, "reason": str(error), "elapsed_seconds": time.monotonic() - started}, indent=2), encoding="utf-8")
        raise
