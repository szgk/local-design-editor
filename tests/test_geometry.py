import json

import numpy as np
import pytest
from PIL import Image

from design_editor.geometry import replace_shape
from design_editor.pipeline import run, digest
from design_editor.review import record_review
from design_editor.validation import evaluate
from examples.create_sample import create


def test_published_evidence_matches_reviewed_result():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "examples"
    for name in ("square", "textile"):
        report = json.loads((root / (name + "-validation.json")).read_text())
        review = json.loads((root / (name + "-review.json")).read_text())
        assert digest(root / (name + "-result.png")) == report["result_sha256"] == review["result_sha256"]
        assert digest(root / (name + "-validation.json")) == review["validation_sha256"]
        assert review["status"] == "accepted"
        assert report["protected_changed_pixels"] == 0


def test_original_unmet_square_task_and_independent_raster_oracle(tmp_path):
    create(tmp_path)
    spec = json.loads((tmp_path / "square.json").read_text())
    spec["source"] = str(tmp_path / spec["source"])
    spec["editable_mask"] = str(tmp_path / spec["editable_mask"])
    directory, report = run(spec, tmp_path / "runs")
    original = np.array(Image.open(spec["source"]))
    result = np.array(Image.open(directory / "result.png"))
    # Independent per-pixel expected raster; do not call the drawing implementation.
    for y in range(512):
        for x in range(512):
            if 240 <= x <= 272 and 376 <= y <= 408:
                assert tuple(result[y, x]) == (221, 51, 51, 255)
            elif 230 <= x <= 282 and 366 <= y <= 418:
                assert tuple(result[y, x]) == (166, 189, 201, 255)
            else:
                assert np.array_equal(result[y, x], original[y, x])
    assert report["expectations"]["pass"]
    assert report["expectations"]["checks"][0]["center"] == [256.0, 392.0]
    assert report["protected_changed_pixels"] == 0
    assert report["source_unchanged"]
    assert report["intent_review"] == "pending"
    second, _ = run(spec, tmp_path / "runs")
    assert digest(directory / "result.png") == digest(second / "result.png")


@pytest.mark.parametrize("mask_value", [0, 128, 254])
def test_exact_shape_cannot_be_clipped_by_permission_or_feather(mask_value):
    image = Image.new("RGBA", (8, 8), (1, 2, 3, 90))
    mask = np.full((8, 8), 255, np.uint8)
    mask[2, 2] = mask_value
    with pytest.raises(ValueError, match="full edit permission"):
        replace_shape(image, mask, {"kind": "rectangle", "erase_box": [1, 1, 7, 7], "box": [3, 3, 5, 5], "background": [1, 2, 3], "fill": [4, 5, 6]})


def test_evaluator_rejects_noop_ring_dot_shift_and_color_error():
    original = Image.new("RGBA", (12, 12), (100, 100, 100, 70))
    expected = [
        {"kind": "solid_rectangle", "box": [4, 4, 8, 8], "rgb": [200, 0, 0]},
        {"kind": "solid_rectangle", "box": [0, 0, 12, 4], "rgb": [100, 100, 100]},
        {"kind": "alpha_unchanged"},
    ]
    good = np.array(original)
    good[4:8, 4:8, :3] = [200, 0, 0]
    assert evaluate(original, Image.fromarray(good), expected)["pass"]
    assert not evaluate(original, original, expected)["pass"]
    for wrong in ([100, 100, 100, 70], [255, 255, 255, 70], [201, 0, 0, 70], [200, 0, 0, 71]):
        bad = good.copy()
        bad[5, 5] = wrong
        assert not evaluate(original, Image.fromarray(bad), expected)["pass"]
    shifted = np.roll(good, 1, axis=1)
    assert not evaluate(original, Image.fromarray(shifted), expected)["pass"]


def test_failed_expectation_is_not_accepted_as_success(tmp_path):
    create(tmp_path)
    spec = {"mode": "recolor", "source": str(tmp_path / "robot.png"), "editable_mask": str(tmp_path / "indicator-mask.png"), "hue": 0, "expectations": [{"kind": "solid_rectangle", "box": [240, 376, 273, 409], "rgb": [0, 255, 0]}]}
    directory, report = run(spec, tmp_path / "runs")
    assert report["pixel_preservation_pass"]
    assert report["overall_status"] == "failed"
    with pytest.raises(ValueError, match="Cannot accept"):
        record_review(directory, "accepted", "test", "wrong green square", report["result_sha256"])


def test_review_is_hash_bound_and_append_only(tmp_path):
    create(tmp_path)
    spec = {"mode": "extract", "source": str(tmp_path / "robot.png"), "box": [112, 62, 400, 338]}
    directory, report = run(spec, tmp_path / "runs")
    before = (directory / "validation.json").read_bytes()
    with pytest.raises(ValueError, match="hash"):
        record_review(directory, "accepted", "test", "head visible", "0" * 64)
    first = record_review(directory, "accepted", "test", "head visible", report["result_sha256"])
    second = record_review(directory, "rejected", "test", "alternative review", report["result_sha256"])
    assert first != second
    assert (directory / "validation.json").read_bytes() == before
    assert json.loads(first.read_text())["status"] == "accepted"
