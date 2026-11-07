"""Small audited bilingual command grammar over a user-owned region catalog."""
import copy
import re
from pathlib import Path

from PIL import Image

from .imaging import load
from .regions import select, describe


COLORS = {"red": 0, "赤": 0, "green": 60, "緑": 60, "blue": 120, "青": 120, "yellow": 30, "黄": 30, "purple": 150, "紫": 150}


def interpret(instruction, catalog):
    text = instruction.strip().lower()
    clauses = re.split(r"[;；]", text)
    if any(not re.match(r"\s*(?:preserve\b|keep\b|.*(?:維持|保持|保つ))", clause) for clause in clauses[1:]):
        raise ValueError("Additional edit clauses require separate explicit requests")
    # Preserve clauses are constraints, never additional edit targets.
    action = re.split(r"[;；]|、(?:他|それ以外)|\b(?:and )?(?:preserve|keep)\b", text)[0].strip()
    if any(word in action for word in ("don't", "do not", "しない", "以外", "except")):
        raise ValueError("Negated or exclusion-based edits require an explicit structured request")
    targets = []
    for name, region in catalog["regions"].items():
        aliases = [name, *region.get("aliases", [])]
        if any(re.search(r"(?<!\w)" + re.escape(alias.lower()) + r"(?!\w)", action) if alias.isascii() else alias in action for alias in aliases):
            targets.append(name)
    if len(targets) != 1:
        raise ValueError("Instruction must identify exactly one registered region")
    target = targets[0]
    region = catalog["regions"][target]
    remainder = action
    for alias in sorted([target, *region.get("aliases", [])], key=len, reverse=True):
        remainder = remainder.replace(alias.lower(), " ")
    remainder = re.sub(r"\b(?:change|recolor|make|extract|crop|add|replace|redesign|pattern|marking|the|only|color|to|with|a|small|square|texture|fabric|linen|woven|light|insert|red|green|blue|yellow|purple)\b", " ", remainder)
    remainder = re.sub(r"の色|だけ|変更|変える|変え|する|抽出|切り抜き|正方形|四角|質感|布地|織り|模様|再設計|柄|を|に|赤|青|緑|黄|紫", " ", remainder)
    if re.search(r"\w", remainder):
        raise ValueError("Instruction contains unsupported qualifiers; use an explicit structured request")
    operations = []
    if re.search(r"\b(?:extract|crop)\b|抽出|切り抜", action):
        operations.append("extract")
    if re.search(r"\bsquare\b|四角|正方形", action):
        operations.append("geometry")
    if re.search(r"\b(?:texture|fabric|linen)\b|質感|布地|織り", action):
        operations.append("inpaint")
    if re.search(r"\b(?:redesign|pattern|marking)\b|模様|再設計|柄", action):
        operations.append("redesign")
    if re.search(r"\b(?:generate|create new)\b|新規生成", action):
        raise ValueError("New generation requires the separate generate command and design standard")
    colors = {hue for name, hue in COLORS.items() if re.search(r"\b" + name + r"\b", action) if name.isascii()}
    colors |= {hue for name, hue in COLORS.items() if not name.isascii() and name in action}
    if not operations and colors and re.search(r"\b(?:recolor|change|make)\b|変更|変え|する", action):
        operations.append("recolor")
    if len(operations) != 1:
        raise ValueError("Unsupported or ambiguous edit operation; use a structured request")
    mode = operations[0]
    spec = {"mode": mode, "instruction": instruction, "source": catalog["source"], "target": target, "protected_constraints": ["Preserve every pixel outside the selected region"]}
    if mode == "recolor":
        if len(colors) != 1:
            raise ValueError("Specify exactly one destination color")
        spec["hue"] = colors.pop()
    elif mode == "geometry":
        if "geometry" not in region:
            raise ValueError("This target has no explicit approved geometry preset")
        spec["geometry"] = copy.deepcopy(region["geometry"])
        if colors:
            import cv2
            import numpy as np
            hue = int(cv2.cvtColor(np.array([[spec["geometry"]["fill"]]], dtype=np.uint8), cv2.COLOR_RGB2HSV)[0, 0, 0])
            if len(colors) != 1 or min(abs(hue - next(iter(colors))), 180 - abs(hue - next(iter(colors)))) > 4:
                raise ValueError("Requested color differs from the approved geometry preset")
        spec["expectations"] = copy.deepcopy(region.get("expectations", []))
    elif mode in ("inpaint", "redesign"):
        if "parameters" not in region:
            raise ValueError("This target has no approved synthesis preset")
        spec["parameters"] = copy.deepcopy(region["parameters"])
        if colors and not colors <= set(region.get("approved_hues", [])):
            raise ValueError("The requested synthesis color is not in the approved preset")
    spec["quality"] = copy.deepcopy(region.get("quality", {}))
    return spec


def plan(instruction, catalog, base, output):
    spec = interpret(instruction, catalog)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    image = load(Path(base) / catalog["source"])
    region = catalog["regions"][spec.pop("target")]
    selector = region.get("selectors", {}).get(spec["mode"], region["selector"])
    mask = select(image, selector)
    Image.fromarray(mask).save(output / "editable.png")
    if region.get("protected_selector"):
        protected = select(image, region["protected_selector"])
        Image.fromarray(protected).save(output / "protected.png")
        spec["protected_mask"] = str((output / "protected.png").resolve())
    if spec["mode"] == "extract":
        spec["box"] = describe(mask)["bbox"]
    spec["source"] = str((Path(base) / catalog["source"]).resolve())
    spec["editable_mask"] = str((output / "editable.png").resolve())
    spec["detection"] = {"selector": selector, **describe(mask)}
    return spec
