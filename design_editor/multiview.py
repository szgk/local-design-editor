"""Compare observable landmarks in a declared orthographic coordinate system."""
import numpy as np

from .imaging import load
from .regions import select, describe


AXES = {"front": ("x", 1), "back": ("x", -1), "left": ("z", 1), "right": ("z", -1)}


def measure_view(image, view, spec):
    if view not in AXES or spec.get("projection") != "orthographic":
        raise ValueError("Declare front/back/left/right and orthographic projection")
    scale = spec["pixels_per_unit"]
    if not np.isfinite(scale) or scale <= 0:
        raise ValueError("pixels_per_unit must be positive")
    origin = spec["origin"]
    points = {}
    for name, landmark in spec["landmarks"].items():
        info = describe(select(image, landmark["selector"]))
        method = landmark.get("measure", "center")
        point = list(info["center"])
        if method == "top":
            point[1] = info["bbox"][1]
        elif method == "bottom":
            point[1] = info["bbox"][3] - 1
        elif method != "center":
            raise ValueError("Unknown landmark measurement")
        axis, sign = AXES[view]
        points[name] = {"pixel": point, "coordinates": {axis: sign * (point[0] - origin[0]) / scale, "y": (origin[1] - point[1]) / scale}, "provenance": "image_selector"}
    return points


def validate_views(spec, base):
    from pathlib import Path
    measurements, errors = {}, []
    for view, data in spec["views"].items():
        try:
            measurements[view] = measure_view(load(Path(base) / data["image"]), view, data)
        except (ValueError, KeyError) as error:
            errors.append({"view": view, "reason": str(error)})
    checks = []
    for rule in spec.get("alignments", []):
        values, missing = {}, []
        for view in rule["views"]:
            point = measurements.get(view, {}).get(rule["landmark"], {})
            value = point.get("coordinates", {}).get(rule["axis"])
            if value is None:
                missing.append(view)
            else:
                values[view] = value
        spread = max(values.values()) - min(values.values()) if len(values) >= 2 else None
        checks.append({"landmark": rule["landmark"], "axis": rule["axis"], "values": values, "missing": missing, "spread": spread, "pass": not missing and spread is not None and spread <= rule["tolerance"]})
    occlusion = []
    for rule in spec.get("visibility", []):
        image = load(Path(base) / spec["views"][rule["view"]]["image"])
        selector = dict(rule["selector"], min_area=0)
        area = describe(select(image, selector))["area"]
        occlusion.append({"view": rule["view"], "feature": rule["feature"], "area": area, "pass": (area > 0) == rule["visible"]})
    passed = bool(checks) and not errors and all(c["pass"] for c in checks + occlusion)
    return {"pass": passed, "status": "measured_constraints_pass" if passed else "failed_or_inconclusive", "measurements": measurements, "checks": checks, "visibility": occlusion, "errors": errors, "unverified": ["hidden surfaces", "3D depth not visible in the supplied projections", "semantic identity beyond declared selectors"], "automatic_other_view_edits": False}


def impact(spec, feature, edited_view):
    views = spec.get("feature_views", {}).get(feature)
    if views is None:
        return {"status": "unknown", "reason": "No cross-view dependency is declared", "automatic_edits": False}
    return {"status": "review_candidates", "views": [v for v in views if v != edited_view], "automatic_edits": False}
