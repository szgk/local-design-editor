from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw


def load(path):
    with Image.open(path) as image:
        if getattr(image, "n_frames", 1) != 1:
            raise ValueError("Animated images are unsupported")
        if image.mode not in ("RGB", "RGBA", "L", "P"):
            raise ValueError("Use an 8-bit RGB/RGBA image; color conversion must be explicit")
        return image.convert("RGBA")


def mask_load(path, size):
    with Image.open(path) as image:
        if image.size != size:
            raise ValueError("Mask dimensions must match the source")
        return np.array(image.convert("L"))


def make_mask(size, boxes=(), polygons=()):
    image = Image.new("L", size)
    draw = ImageDraw.Draw(image)
    for box in boxes:
        x0, y0, x1, y1 = box
        if not (0 <= x0 < x1 <= size[0] and 0 <= y0 < y1 <= size[1]):
            raise ValueError("Boxes use bounded, half-open pixel coordinates")
        draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=255)
    for polygon in polygons:
        if len(polygon) < 3 or any(not (0 <= x < size[0] and 0 <= y < size[1]) for x, y in polygon):
            raise ValueError("Invalid polygon")
        draw.polygon([tuple(p) for p in polygon], fill=255)
    return image


def effective_mask(editable, protected=None, feather=0):
    if not np.isfinite(feather) or feather < 0:
        raise ValueError("Feather must be finite and nonnegative")
    mask = editable.copy()
    if protected is not None:
        mask[protected > 0] = 0
    if not mask.any():
        raise ValueError("Editable region is empty")
    if feather:
        support = np.pad((mask > 0).astype(np.uint8), 1)
        distance = cv2.distanceTransform(support, cv2.DIST_L2, 5)[1:-1, 1:-1]
        mask = np.rint(mask * np.minimum(distance / feather, 1)).astype(np.uint8)
    return mask


def composite(original, generated, mask):
    if original.size != generated.size or mask.shape != (original.height, original.width):
        raise ValueError("Source, candidate and mask dimensions must match")
    a, b = np.array(original), np.array(generated)
    # Integer arithmetic avoids floating point drift. Copy protected RGBA verbatim.
    weight = mask.astype(np.uint32)[..., None]
    result = ((a.astype(np.uint32) * (255 - weight) + b.astype(np.uint32) * weight + 127) // 255).astype(np.uint8)
    result[mask == 0] = a[mask == 0]
    return Image.fromarray(result)


def recolor(image, hue):
    if not 0 <= hue <= 179:
        raise ValueError("OpenCV hue must be in 0..179")
    rgba = np.array(image)
    hsv = cv2.cvtColor(rgba[..., :3], cv2.COLOR_RGB2HSV)
    hsv[..., 0] = hue
    rgba[..., :3] = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)
    return Image.fromarray(rgba)


def crop(image, box):
    make_mask(image.size, [box])  # validate; never pad or invent hidden pixels
    return image.crop(tuple(box))
