"""Original generic geometric fixture; no external artwork or model required."""
import json
from pathlib import Path

from PIL import Image, ImageDraw


def create(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", (512, 512), (245, 242, 235, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((120, 70, 392, 330), radius=40, fill="#a6bdc9", outline="#253640", width=8)
    draw.rectangle((170, 330, 342, 470), fill="#a6bdc9", outline="#253640", width=8)
    draw.ellipse((172, 164, 212, 204), fill="#253640")
    draw.ellipse((300, 164, 340, 204), fill="#253640")
    draw.rectangle((216, 256, 296, 268), fill="#253640")
    draw.ellipse((238, 374, 274, 410), fill="#3399dd")
    image.save(root / "robot.png")
    mask = Image.new("L", image.size)
    ImageDraw.Draw(mask).ellipse((238, 374, 274, 410), fill=255)
    mask.save(root / "indicator-mask.png")
    region = Image.new("L", image.size)
    ImageDraw.Draw(region).rectangle((224, 360, 288, 424), fill=255)
    region.save(root / "panel-mask.png")
    for name, request in {
        "recolor": {"mode": "recolor", "source": "robot.png", "editable_mask": "indicator-mask.png", "hue": 0, "instruction": "Change only the circular status indicator from blue to red", "protected_constraints": ["Preserve all shapes, placement and other colors"]},
        "inpaint": {"mode": "inpaint", "source": "robot.png", "editable_mask": "panel-mask.png", "feather": 3, "instruction": "Replace the circular status indicator with a small square status indicator", "protected_constraints": ["Preserve the robot silhouette, face, body and background"], "parameters": {"checkpoint": "sd-v1-5-inpainting.ckpt", "prompt": "flat geometric robot illustration, small red square status indicator centered on blue gray chest panel, simple matte colors, clean edges", "negative_prompt": "text, shading, photorealistic, extra buttons", "seed": 42, "steps": 20, "cfg": 6, "denoise": 0.85}},
        "extract": {"mode": "extract", "source": "robot.png", "box": [112, 62, 400, 338], "instruction": "Crop the visible robot head without filling hidden surfaces"},
    }.items():
        if name == "inpaint":
            request["parameters"].update(context_box=[192, 328, 320, 456], context_resolution=512, denoise=1.0, cfg=8, seed=7, prompt="a bright red square button, solid red square, flat vector illustration, blue grey background")
        (root / (name + ".json")).write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")
    request = json.loads((root / "inpaint.json").read_text())
    request["instruction"] = "Remove only the circular status indicator and restore the plain chest panel"
    request["parameters"].update(prompt="plain uniform blue grey panel, flat solid blue grey color, minimalist vector art", negative_prompt="button, indicator, circle, ring, hole, dot, highlight, text, shadow", seed=42)
    request["parameters"].pop("context_box")
    request["parameters"].pop("context_resolution")
    (root / "remove-indicator.json").write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")
    request = {
        "mode": "geometry", "source": "robot.png", "editable_mask": "panel-mask.png",
        "instruction": "Replace the circular indicator with a centered 33 by 33 pixel solid red square; keep the panel flat and preserve everything else",
        "protected_constraints": ["Keep the silhouette, face, body, background, alpha and indicator center unchanged"],
        "geometry": {"kind": "rectangle", "erase_box": [230, 366, 283, 419], "box": [240, 376, 273, 409], "background": [166, 189, 201], "fill": [221, 51, 51]},
        "expectations": [
            {"kind": "solid_rectangle", "box": [240, 376, 273, 409], "rgb": [221, 51, 51]},
            *[{"kind": "solid_rectangle", "box": box, "rgb": [166, 189, 201]} for box in ([230, 366, 283, 376], [230, 409, 283, 419], [230, 376, 240, 409], [273, 376, 283, 409])],
            {"kind": "unchanged_outside_box", "box": [230, 366, 283, 419]},
            {"kind": "alpha_unchanged"},
        ],
    }
    (root / "square.json").write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")
    surface_mask = Image.new("L", image.size)
    ImageDraw.Draw(surface_mask).rectangle((208, 348, 303, 443), fill=255)
    surface_mask.save(root / "surface-mask.png")
    request = {
        "mode": "inpaint", "source": "robot.png", "editable_mask": "surface-mask.png", "feather": 0,
        "instruction": "Replace only the masked chest surface, including its circular indicator, with a light blue woven textile insert",
        "protected_constraints": ["Preserve the head, face, body silhouette, other panel areas and background"],
        "parameters": {"checkpoint": "sd-v1-5-inpainting.ckpt", "prompt": "macro photograph of light blue woven linen fabric, visible woven threads and fibers, matte textile texture", "negative_prompt": "smooth, flat color, illustration, plastic, metal, circle, button, text", "seed": 42, "steps": 20, "cfg": 7, "denoise": 1.0, "context_box": [208, 348, 304, 444], "context_resolution": 512},
    }
    (root / "textile.json").write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    create(Path(__file__).parent)
