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
