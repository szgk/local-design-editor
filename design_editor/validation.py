import numpy as np
from PIL import Image


def verify(original, result, editable, protected=None):
    if original.size != result.size:
        return {"pixel_preservation_pass": False, "reason": "resolution_changed"}, None
    a, b = np.array(original), np.array(result)
    delta = np.abs(a.astype(np.int16) - b.astype(np.int16)).astype(np.uint8)
    changed = np.any(delta != 0, axis=2)
    forbidden = editable == 0
    if protected is not None:
        forbidden |= protected > 0
    count = int(np.count_nonzero(changed & forbidden))
    heat = np.zeros_like(a)
    heat[..., 0] = np.max(delta, axis=2)
    heat[..., 3] = 255
    return {
        "pixel_preservation_pass": count == 0,
        "protected_changed_pixels": count,
        "protected_max_channel_delta": int(delta[forbidden].max()) if forbidden.any() else 0,
        "changed_pixels": int(changed.sum()),
        "editable_changed_pixels": int((changed & ~forbidden).sum()),
        "resolution_preserved": True,
        "intent_review": "pending",
        "overall_status": "needs_visual_review" if count == 0 else "failed",
    }, Image.fromarray(heat)


def evaluate(original, result, expectations):
    """Independent acceptance constraints, never used to generate the candidate."""
    from .geometry import rectangle
    checks = []
    a, b = np.array(original), np.array(result)
    for expected in expectations:
        kind = expected["kind"]
        if kind == "solid_rectangle":
            left, top, right, bottom = rectangle(result.size, expected["box"])
            region = b[top:bottom, left:right, :3]
            exact = np.all(region == expected["rgb"], axis=2)
            checks.append({"kind": kind, "pass": bool(exact.all()), "matching_pixels": int(exact.sum()), "required_pixels": int(exact.size), "center": [(left + right - 1) / 2, (top + bottom - 1) / 2], "size": [right - left, bottom - top]})
        elif kind == "patch_palette":
            left, top, right, bottom = rectangle(result.size, expected["box"])
            region = b[top:bottom, left:right, :3]
            valid = np.zeros(region.shape[:2], bool)
            for color in expected["rgb_colors"]:
                valid |= np.all(region == color, axis=2)
            checks.append({"kind": kind, "pass": bool(valid.all()), "unexpected_pixels": int((~valid).sum())})
        elif kind == "unchanged_outside_box":
            left, top, right, bottom = rectangle(result.size, expected["box"])
            outside = np.ones(b.shape[:2], bool)
            outside[top:bottom, left:right] = False
            count = int(np.any(a != b, axis=2)[outside].sum())
            checks.append({"kind": kind, "pass": count == 0, "changed_pixels": count})
        elif kind == "alpha_unchanged":
            count = int(np.count_nonzero(a[..., 3] != b[..., 3]))
            checks.append({"kind": kind, "pass": count == 0, "changed_pixels": count})
        else:
            raise ValueError("Unknown expectation: " + str(kind))
    return {"pass": all(check["pass"] for check in checks), "checks": checks}
