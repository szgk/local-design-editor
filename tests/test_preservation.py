import json

import numpy as np
import pytest
from PIL import Image

from design_editor.imaging import composite, effective_mask, make_mask, crop
from design_editor.validation import verify
from design_editor.pipeline import run
from design_editor.comfy import workflow, ComfyBackend


def test_arbitrary_rgba_exact_outside_mask():
    rng = np.random.default_rng(8)
    a = Image.fromarray(rng.integers(0, 256, (31, 29, 4), dtype=np.uint8))
    b = Image.fromarray(rng.integers(0, 256, (31, 29, 4), dtype=np.uint8))
    m = np.zeros((31, 29), np.uint8)
    m[5:15, 8:20] = 255
    protected = np.zeros_like(m)
    protected[8:10, :] = 255
    weight = effective_mask(m, protected, 4)
    result = composite(a, b, weight)
    report, _ = verify(a, result, m, protected)
    assert report["protected_changed_pixels"] == 0
    assert report["changed_pixels"] > 0
    assert np.all(weight[m == 0] == 0)
    assert np.all(weight[protected > 0] == 0)


def test_verifier_detects_alpha_and_rgb_leaks():
    a = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    b = a.copy()
    b.putpixel((0, 0), (0, 0, 0, 1))
    b.putpixel((1, 1), (1, 0, 0, 0))
    report, _ = verify(a, b, np.zeros((4, 4), np.uint8))
    assert not report["pixel_preservation_pass"]
    assert report["protected_changed_pixels"] == 2


def test_crop_and_coordinate_bounds():
    image = Image.new("RGBA", (8, 8), "red")
    assert crop(image, [2, 3, 6, 7]).size == (4, 4)
    assert np.count_nonzero(make_mask(image.size, [[2, 3, 6, 7]])) == 16
    with pytest.raises(ValueError):
        crop(image, [-1, 0, 4, 4])


def test_invalid_dimensions_and_empty_mask():
    with pytest.raises(ValueError):
        composite(Image.new("RGBA", (8, 8)), Image.new("RGBA", (9, 8)), np.ones((8, 8)))
    with pytest.raises(ValueError):
        effective_mask(np.zeros((8, 8), np.uint8))
    with pytest.raises(ValueError):
        effective_mask(np.ones((8, 8), np.uint8), feather=-1)


def test_history_is_immutable_and_review_pending(tmp_path):
    source = tmp_path / "source.png"
    mask = tmp_path / "mask.png"
    Image.new("RGBA", (8, 8), (0, 0, 255, 90)).save(source)
    make_mask((8, 8), [[2, 2, 6, 6]]).save(mask)
    before = source.read_bytes()
    spec = {"source": str(source), "editable_mask": str(mask), "mode": "recolor", "hue": 0}
    first, report = run(spec, tmp_path / "runs")
    second, _ = run(spec, tmp_path / "runs")
    assert first != second
    assert source.read_bytes() == before
    assert report["intent_review"] == "pending"
    assert report["pixel_preservation_pass"]
    assert report["editable_changed_pixels"] == 16
    assert Image.open(first / "result.png").getpixel((3, 3))[3] == 90


def test_failure_is_saved(tmp_path):
    with pytest.raises(FileNotFoundError):
        run({"source": str(tmp_path / "missing.png"), "mode": "extract"}, tmp_path / "runs")
    assert len(list((tmp_path / "runs").glob("*/failure.json"))) == 1


def test_extract_transparency_preserves_rgb_and_existing_alpha(tmp_path):
    source, mask = tmp_path / "source.png", tmp_path / "mask.png"
    Image.new("RGBA", (8, 8), (100, 150, 200, 90)).save(source)
    make_mask((8, 8), [[3, 3, 5, 5]]).save(mask)
    directory, _ = run({"source": str(source), "editable_mask": str(mask), "mode": "extract", "box": [2, 2, 6, 6]}, tmp_path / "runs")
    result = Image.open(directory / "result.png")
    assert result.getpixel((0, 0)) == (100, 150, 200, 0)
    assert result.getpixel((1, 1)) == (100, 150, 200, 90)


def test_backend_contract(tmp_path):
    image = tmp_path / "source.png"
    mask = tmp_path / "mask.png"
    Image.new("RGBA", (17, 19), "blue").save(image)
    make_mask((17, 19), [[2, 2, 8, 8]]).save(mask)
    class Fake:
        def generate(self, image, mask, parameters, directory):
            return Image.new("RGBA", image.size, "red")
    _, report = run({"mode": "inpaint", "source": str(image), "editable_mask": str(mask), "parameters": {}}, tmp_path / "runs", Fake())
    assert report["protected_changed_pixels"] == 0
    assert report["editable_changed_pixels"] == 36


def test_workflow_uses_inpainting_conditioning_and_local_only():
    graph = workflow("source.png", "mask.png", {"checkpoint": "inpaint.ckpt", "prompt": "square"})
    assert graph["6"]["class_type"] == "InpaintModelConditioning"
    assert graph["3"]["inputs"]["channel"] == "red"
    with pytest.raises(ValueError):
        ComfyBackend("https://example.com")


def test_context_rejects_excluded_edits_before_network(tmp_path):
    image = Image.new("RGBA", (32, 32), "blue")
    mask = make_mask(image.size, [[20, 20, 25, 25]])
    with pytest.raises(ValueError, match="entire editable mask"):
        ComfyBackend().generate(image, mask, {"context_box": [0, 0, 16, 16]}, tmp_path)


def test_context_rejects_aspect_distortion(tmp_path):
    image = Image.new("RGBA", (32, 32), "blue")
    mask = make_mask(image.size, [[2, 2, 4, 4]])
    with pytest.raises(ValueError, match="square"):
        ComfyBackend().generate(image, mask, {"context_box": [0, 0, 16, 24]}, tmp_path)
