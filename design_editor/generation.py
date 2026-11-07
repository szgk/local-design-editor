"""Explicit new-design generation, separate from editing an existing source."""
import json
from pathlib import Path
import uuid

from PIL import Image, ImageDraw

from .comfy import ComfyBackend


def _generate(spec, root="runs", backend=None, directory=None):
    directory = directory or Path(root) / ("generation-" + uuid.uuid4().hex)
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "standard.json").write_text(json.dumps(spec, indent=2), encoding="utf-8")
    engine = spec.get("engine", "geometric")
    if engine not in ("geometric", "comfy"):
        raise ValueError("Unknown generation engine")
    width, height = spec["size"]
    if any(type(v) is not int or not 64 <= v <= 2048 for v in (width, height)):
        raise ValueError("Canvas size must be 64..2048")
    views = spec.get("views", ["front", "left", "right", "back"])
    if not views or len(set(views)) != len(views) or not set(views) <= {"front", "left", "right", "back"}:
        raise ValueError("Declare unique object-relative view names")
    output = {}
    for view in views:
        image = Image.new("RGBA", (width, height), tuple(spec["background"]))
        if engine == "geometric":
            # Templates are declared individually; shared dimension names ensure equal scales.
            for part in spec["parts"]:
                if view not in part["views"]:
                    continue
                left, top, right, bottom = part["views"][view]
                if not (0 <= left < right <= width and 0 <= top < bottom <= height):
                    raise ValueError("Generated part exceeds the standard canvas")
                draw = ImageDraw.Draw(image)
                if part["shape"] == "rectangle":
                    draw.rectangle((left, top, right - 1, bottom - 1), fill=tuple(spec["palette"][part["color"]]))
                elif part["shape"] == "ellipse":
                    draw.ellipse((left, top, right - 1, bottom - 1), fill=tuple(spec["palette"][part["color"]]))
                else:
                    raise ValueError("Unknown geometric primitive")
        else:
            child = directory / view
            child.mkdir()
            parameters = dict(spec["parameters"])
            parameters["prompt"] = spec["description"] + ", " + view + " orthographic view, " + spec.get("style", "flat geometric character illustration")
            image = (backend or ComfyBackend(timeout=spec.get("timeout", 300))).generate(image, Image.new("L", image.size, 255), parameters, child)
        image.save(directory / (view + ".png"))
        output[view] = view + ".png"
    from .pipeline import digest
    report = {"operation": "new_generation", "engine": engine, "views": output, "result_hashes": {v: digest(directory / p) for v, p in output.items()}, "source_preservation_claim": False, "status": "needs_visual_review", "cross_view_consistency": "requires declared landmark verification"}
    sheet = Image.new("RGBA", (width * len(views), height))
    for i, view in enumerate(views):
        with Image.open(directory / output[view]) as image:
            sheet.paste(image, (i * width, 0))
    sheet.save(directory / "views.png")
    report["sheet_sha256"] = digest(directory / "views.png")
    (directory / "generation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return directory, report


def generate(spec, root="runs", backend=None):
    directory = Path(root) / ("generation-" + uuid.uuid4().hex)
    try:
        return _generate(spec, root, backend, directory)
    except Exception as error:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "failure.json").write_text(json.dumps({"status": "failed", "type": type(error).__name__, "reason": str(error)}, indent=2), encoding="utf-8")
        raise
