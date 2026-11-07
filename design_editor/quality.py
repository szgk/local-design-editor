"""Measured 2-D geometry; none of these measurements reconstruct hidden 3-D."""
import cv2
import numpy as np

from .regions import select, describe


def boundary_metrics(original, result, mask):
    """RGB jumps across editable/protected adjacency, not a semantic seam verdict."""
    support = mask > 0
    values = []
    for image in (original, result):
        pixels = np.array(image)[..., :3].astype(np.float32)
        horizontal = support[:, 1:] != support[:, :-1]
        vertical = support[1:] != support[:-1]
        samples = np.concatenate((np.abs(pixels[:, 1:] - pixels[:, :-1])[horizontal].ravel(), np.abs(pixels[1:] - pixels[:-1])[vertical].ravel()))
        values.append(float(samples.mean()) if len(samples) else None)
    return {"reference_mean_rgb_jump": values[0], "result_mean_rgb_jump": values[1], "increase": values[1] - values[0] if values[0] is not None else None, "interpretation": "measured adjacency only; intentional material boundaries may have a large jump"}


def contours(mask):
    binary = (mask > 0).astype(np.uint8)
    return binary.astype(bool) & ~cv2.erode(binary, np.ones((3, 3), np.uint8), borderType=cv2.BORDER_CONSTANT, borderValue=0).astype(bool)


def compare_masks(reference, result):
    if reference.shape != result.shape:
        raise ValueError("Contour comparison requires identical coordinate systems")
    a, b = reference > 0, result > 0
    union = np.count_nonzero(a | b)
    if not a.any() or not b.any():
        return {"iou": 1.0 if not union else 0.0, "hausdorff_pixels": None, "mean_contour_distance_pixels": None, "measured": False}
    ca, cb = contours(a), contours(b)
    da = cv2.distanceTransform((~ca).astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    db = cv2.distanceTransform((~cb).astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    return {"iou": float(np.count_nonzero(a & b) / union), "hausdorff_pixels": float(max(db[ca].max(), da[cb].max())), "mean_contour_distance_pixels": float((db[ca].mean() + da[cb].mean()) / 2), "measured": True}


def symmetry(mask, axis_x, excluded_boxes=()):
    height, width = mask.shape
    if not np.isfinite(axis_x) or 2 * axis_x != round(2 * axis_x):
        raise ValueError("Symmetry axis must lie on a pixel center or half-pixel boundary")
    xx = np.arange(width)
    mirrored = np.rint(2 * axis_x - xx).astype(int)
    valid_x = (mirrored >= 0) & (mirrored < width)
    valid = np.tile(valid_x, (height, 1))
    for left, top, right, bottom in excluded_boxes:
        from .geometry import rectangle
        rectangle((width, height), [left, top, right, bottom])
        valid[top:bottom, left:right] = False
    # Exclude both members of an explicitly asymmetric pair.
    valid &= valid[:, np.clip(mirrored, 0, width - 1)]
    source = mask > 0
    target = source[:, np.clip(mirrored, 0, width - 1)]
    union = (source | target) & valid
    count = int(union.sum())
    return {"axis_x": axis_x, "mismatch_fraction": float(((source != target) & valid).sum() / count) if count else None, "compared_foreground_pixels": count}


def assess(original, result, spec):
    checks = []
    if spec.get("silhouette"):
        rule = spec["silhouette"]
        reference = select(original, rule["selector"])
        try:
            metrics = compare_masks(reference, select(result, rule["selector"]))
            passed = metrics["measured"] and metrics["iou"] >= rule.get("min_iou", 1.0) and metrics["hausdorff_pixels"] <= rule.get("max_hausdorff", 0)
        except ValueError as error:
            metrics = {"measured": False, "reason": str(error)}
            passed = False
        checks.append({"kind": "silhouette", "pass": bool(passed), **metrics})
    for name, rule in spec.get("landmarks", {}).items():
        try:
            measurement = describe(select(result, rule["selector"]))
            center = measurement["center"]
            error = float(np.linalg.norm(np.array(center) - rule["expected"]))
            passed = error <= rule.get("tolerance", 0)
            if "area_range" in rule:
                passed &= rule["area_range"][0] <= measurement["area"] <= rule["area_range"][1]
            box = measurement["bbox"]
            measurement["aspect_ratio"] = (box[2] - box[0]) / (box[3] - box[1])
            if "expected_aspect_ratio" in rule:
                passed &= abs(measurement["aspect_ratio"] - rule["expected_aspect_ratio"]) <= rule.get("aspect_tolerance", 0)
            checks.append({"kind": "landmark", "name": name, "pass": bool(passed), "position_error_pixels": error, **measurement})
        except ValueError as error:
            checks.append({"kind": "landmark", "name": name, "pass": False, "reason": str(error)})
    if spec.get("symmetry"):
        rule = spec["symmetry"]
        metrics = symmetry(select(result, rule["selector"]), rule["axis_x"], rule.get("excluded_boxes", ()))
        checks.append({"kind": "symmetry", "pass": metrics["mismatch_fraction"] is not None and metrics["mismatch_fraction"] <= rule.get("max_mismatch", 0), **metrics})
    if "min_changed_pixels" in spec:
        count = int(np.any(np.array(original) != np.array(result), axis=2).sum())
        checks.append({"kind": "change", "pass": count >= spec["min_changed_pixels"], "changed_pixels": count})
    if spec.get("edge_preservation"):
        from .geometry import rectangle
        rule = spec["edge_preservation"]
        left, top, right, bottom = rectangle(result.size, rule["box"])
        def edges(image):
            gray = cv2.cvtColor(np.array(image)[top:bottom, left:right, :3], cv2.COLOR_RGB2GRAY)
            return cv2.Canny(gray, rule.get("low", 20), rule.get("high", 60)) > 0
        before, after = edges(original), edges(result)
        measured = bool(before.any() and after.any())
        distance = cv2.distanceTransform((~after).astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
        mean = float(distance[before].mean()) if measured else None
        checks.append({"kind": "edge_preservation", "pass": measured and mean <= rule["max_mean_distance"], "mean_reference_edge_distance_pixels": mean, "reference_edge_pixels": int(before.sum()), "result_edge_pixels": int(after.sum()), "direction": "reference to result only; extra result edges require separate review"})
    return {"pass": bool(checks) and all(c["pass"] for c in checks), "checks": checks, "intent_review": "pending"}
