"""Explicit, reproducible selectors. Unknown objects are never guessed."""
import cv2
import numpy as np

from .geometry import rectangle


def select(image, selector):
    a = np.array(image.convert("RGBA"))
    kind = selector["kind"]
    if kind == "alpha":
        mask = a[..., 3] > selector.get("threshold", 0)
    elif kind in ("color", "background"):
        rgb = np.asarray(selector["rgb"], dtype=np.int16)
        if rgb.shape != (3,):
            raise ValueError("Selector requires an RGB triple")
        tolerance = selector.get("tolerance", 0)
        if not 0 <= tolerance <= 255:
            raise ValueError("Color tolerance must be 0..255")
        mask = np.max(np.abs(a[..., :3].astype(np.int16) - rgb), axis=2) <= tolerance
        if kind == "background":
            mask = ~mask
        mask &= a[..., 3] > 0
    elif kind == "box":
        mask = np.zeros(a.shape[:2], bool)
        left, top, right, bottom = rectangle(image.size, selector["box"])
        mask[top:bottom, left:right] = True
    else:
        raise ValueError("Unknown region selector: " + str(kind))
    if selector.get("roi"):
        left, top, right, bottom = rectangle(image.size, selector["roi"])
        bounded = np.zeros_like(mask)
        bounded[top:bottom, left:right] = mask[top:bottom, left:right]
        mask = bounded
    if "seed" in selector:
        x, y = selector["seed"]
        if not (0 <= x < image.width and 0 <= y < image.height) or not mask[y, x]:
            raise ValueError("Component seed is outside the selected pixels")
        _, labels = cv2.connectedComponents(mask.astype(np.uint8), connectivity=8)
        mask = labels == labels[y, x]
    area = int(mask.sum())
    if area < selector.get("min_area", 1) or area > selector.get("max_area", image.width * image.height):
        raise ValueError("Region area is outside its declared bounds")
    return mask.astype(np.uint8) * 255


def describe(mask):
    y, x = np.nonzero(mask)
    if not len(x):
        return {"area": 0, "bbox": None, "center": None}
    return {"area": len(x), "bbox": [int(x.min()), int(y.min()), int(x.max()) + 1, int(y.max()) + 1], "center": [float(x.mean()), float(y.mean())]}
