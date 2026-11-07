"""Build public catalogs and orthographic standards from independent geometry."""
import copy
import json
from pathlib import Path

import numpy as np
from PIL import Image

from examples.create_sample import create


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def create_advanced(root):
    root = Path(root)
    create(root)
    square = json.loads((root / "square.json").read_text())
    textile = json.loads((root / "textile.json").read_text())
    quality = {"silhouette": {"selector": {"kind": "background", "rgb": [245, 242, 235]}, "min_iou": 1, "max_hausdorff": 0}, "min_changed_pixels": 1}
    catalog = {"source": "robot.png", "regions": {
        "indicator": {"aliases": ["表示灯"], "selector": {"kind": "color", "rgb": [51, 153, 221], "roi": [220, 356, 292, 428], "min_area": 100, "max_area": 2000}, "selectors": {"geometry": {"kind": "box", "box": [230, 366, 283, 419]}}, "geometry": square["geometry"], "expectations": square["expectations"], "quality": quality},
        "head": {"aliases": ["頭部"], "selector": {"kind": "background", "rgb": [245, 242, 235], "roi": [112, 62, 400, 330]}},
        "surface": {"aliases": ["表面"], "selector": {"kind": "box", "box": [208, 348, 304, 444]}, "parameters": textile["parameters"], "quality": quality},
    }}
    write(root / "catalog.json", catalog)
    other = copy.deepcopy(catalog)
    with Image.open(root / "robot.png") as image:
        pixels = np.array(image.convert("RGBA"))
    pixels[np.all(pixels[..., :3] == [166, 189, 201], axis=2), :3] = [188, 176, 211]
    Image.fromarray(pixels).save(root / "robot-alternative.png")
    other["source"] = "robot-alternative.png"
    other["regions"]["indicator"]["aliases"] = ["ランプ"]
    write(root / "catalog-alternative.json", other)
    write(root / "batch.json", {"instruction": "change indicator to red", "items": [{"catalog": "catalog.json"}, {"catalog": "catalog-alternative.json"}]})
    write(root / "retry.json", {"max_attempts": 3, "changes": [{"cause": "no_change", "parameters": {"denoise": 1.0, "seed": 43}}, {"cause": "insufficient_change", "parameters": {"denoise": 1.0, "seed": 43}}, {"cause": "shape_drift", "parameters": {"denoise": 0.5, "seed": 44}}]})
    write(root / "profiles.json", [
        {"name": "sd15", "parameters": {"family": "sd15", "loader": "checkpoint", "checkpoint": "sd-v1-5-inpainting.ckpt"}, "identity": {"sha256": "c6bbc15e3224e6973459ba78de4998b80b50112b0ae5b5c67113d56b4e366b19"}},
        {"name": "sd15-canny", "parameters": {"family": "sd15", "loader": "checkpoint", "checkpoint": "sd-v1-5-inpainting.ckpt", "controlnet": {"model": "sd15-canny-fp16.safetensors", "family": "sd15", "kind": "canny", "strength": 0.7}}, "identity": {"repository": "lllyasviel/control_v11p_sd15_canny", "revision": "115a470d547982438f70198e353a921996e2e819"}},
        {"name": "sdxl", "parameters": {"family": "sdxl", "loader": "diffusers", "model_path": "sdxl-inpaint"}, "identity": {"repository": "diffusers/stable-diffusion-xl-1.0-inpainting-0.1", "revision": "115134f363124c53c7d878647567d04daf26e41e"}},
    ])
    all_views = ["front", "left", "right", "back"]
    standard = {"engine": "geometric", "size": [256, 256], "views": all_views, "background": [245, 242, 235, 255], "palette": {"body": [166, 189, 201, 255], "detail": [37, 54, 64, 255], "indicator": [51, 153, 221, 255]}, "parts": [
        {"shape": "rectangle", "color": "body", "views": {v: ([64, 32, 192, 144] if v in ("front", "back") else [88, 32, 168, 144]) for v in all_views}},
        {"shape": "rectangle", "color": "body", "views": {v: ([80, 144, 176, 240] if v in ("front", "back") else [104, 144, 152, 240]) for v in all_views}},
        {"shape": "ellipse", "color": "detail", "views": {"front": [90, 72, 102, 84], "left": [124, 72, 136, 84], "right": [120, 72, 132, 84]}},
        {"shape": "ellipse", "color": "detail", "views": {"front": [154, 72, 166, 84]}},
        {"shape": "ellipse", "color": "indicator", "views": {"front": [120, 184, 136, 200]}},
    ]}
    write(root / "standard.json", standard)
    alternate = copy.deepcopy(standard)
    alternate["palette"]["body"] = [188, 176, 211, 255]
    alternate["palette"]["indicator"] = [221, 51, 51, 255]
    write(root / "standard-alternative.json", alternate)
    # Validation references generated files by explicit relative paths supplied in a real run.
    views = {v: {"image": v + ".png", "projection": "orthographic", "pixels_per_unit": 100, "origin": [128, 239], "landmarks": {
        "head_top": {"selector": {"kind": "background", "rgb": [245, 242, 235], "roi": [32, 0, 224, 144]}, "measure": "top"},
        "body_bottom": {"selector": {"kind": "background", "rgb": [245, 242, 235], "roi": [32, 144, 224, 256]}, "measure": "bottom"},
    }} for v in all_views}
    write(root / "views-template.json", {"views": views, "alignments": [{"landmark": feature, "axis": "y", "views": all_views, "tolerance": 0} for feature in ("head_top", "body_bottom")], "visibility": [{"view": v, "feature": "indicator", "selector": {"kind": "color", "rgb": [51, 153, 221]}, "visible": v == "front"} for v in all_views], "feature_views": {"head": all_views, "indicator": ["front"]}})


if __name__ == "__main__":
    create_advanced(Path(__file__).parent)
