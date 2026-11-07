"""Explicit flat-art edits. No automatic segmentation or inferred background."""
import numpy as np
from PIL import Image


def rectangle(size, box):
    if len(box) != 4 or any(type(v) is not int for v in box):
        raise ValueError("Rectangle coordinates must be four integers")
    left, top, right, bottom = box
    if not (0 <= left < right <= size[0] and 0 <= top < bottom <= size[1]):
        raise ValueError("Rectangle must be bounded and nonempty")
    return left, top, right, bottom


def replace_shape(image, mask, spec):
    """Erase an explicit flat patch, then draw a solid rectangle; retain alpha."""
    if spec.get("kind") != "rectangle":
        raise ValueError("Only explicit rectangle geometry is supported")
    erase = rectangle(image.size, spec["erase_box"])
    target = rectangle(image.size, spec["box"])
    if not (erase[0] <= target[0] < target[2] <= erase[2] and erase[1] <= target[1] < target[3] <= erase[3]):
        raise ValueError("Target must be inside the erase box")
    for key in ("background", "fill"):
        color = spec[key]
        if len(color) != 3 or any(type(c) is not int or not 0 <= c <= 255 for c in color):
            raise ValueError("Colors must be explicit 8-bit RGB triples")
    left, top, right, bottom = erase
    if not np.all(mask[top:bottom, left:right] == 255):
        raise ValueError("Exact geometry requires full edit permission throughout erase_box; check protection and feather")
    pixels = np.array(image)
    pixels[top:bottom, left:right, :3] = spec["background"]
    left, top, right, bottom = target
    pixels[top:bottom, left:right, :3] = spec["fill"]
    return Image.fromarray(pixels)
