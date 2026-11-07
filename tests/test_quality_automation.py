import copy
import json

import numpy as np
import pytest
from PIL import Image

from design_editor.quality import compare_masks, symmetry, assess
from design_editor.regions import select
from design_editor.planner import interpret, plan
from design_editor.automation import run_trials
from design_editor.comfy import workflow
from design_editor.multiview import validate_views, impact
from design_editor.batch import execute_batch
from design_editor.generation import generate
from design_editor.benchmark import compare
from design_editor.learning import collect
from examples.create_sample import create


def catalog():
    return {"source": "robot.png", "regions": {"indicator": {"aliases": ["表示灯"], "selector": {"kind": "color", "rgb": [51, 153, 221], "roi": [220, 356, 292, 428], "min_area": 100}}}}


def test_iou_and_hausdorff_are_sensitive_to_real_translation():
    a = np.zeros((40, 40), np.uint8)
    a[10:20, 10:20] = 255
    b = np.roll(a, 3, axis=1)
    result = compare_masks(a, b)
    assert result["hausdorff_pixels"] == 3
    assert result["iou"] == pytest.approx(70 / 130)
    assert compare_masks(a, a)["hausdorff_pixels"] == 0
    assert compare_masks(np.zeros_like(a), a)["measured"] is False


def test_symmetry_and_intentional_asymmetry_exclusion():
    a = np.zeros((20, 20), np.uint8)
    a[4:12, 5:15] = 255
    assert symmetry(a, 9.5)["mismatch_fraction"] == 0
    a[1, 3] = 255
    assert symmetry(a, 9.5)["mismatch_fraction"] > 0
    assert symmetry(a, 9.5, [[3, 1, 4, 2]])["mismatch_fraction"] == 0


def test_selector_rejects_wrong_seed_and_area_and_transparency():
    image = Image.new("RGBA", (10, 10), (0, 0, 255, 0))
    with pytest.raises(ValueError):
        select(image, {"kind": "color", "rgb": [0, 0, 255]})
    with pytest.raises(ValueError):
        select(image, {"kind": "box", "box": [1, 1, 5, 5], "seed": [8, 8]})
    with pytest.raises(ValueError):
        select(image, {"kind": "box", "box": [1, 1, 5, 5], "max_area": 10})


@pytest.mark.parametrize("instruction", ["change indicator to red", "表示灯の色だけ赤に変更"])
def test_bilingual_instruction_and_automatic_region_detection(tmp_path, instruction):
    create(tmp_path)
    spec = plan(instruction, catalog(), tmp_path, tmp_path / "plan")
    assert spec["mode"] == "recolor" and spec["hue"] == 0
    assert spec["detection"]["area"] == 1073
    _, report = run_trials(spec, tmp_path / "runs")
    assert report["status"] == "needs_visual_review"
    assert report["attempts"][0]["report"]["protected_changed_pixels"] == 0
    assert report["accepted"] is False


@pytest.mark.parametrize("instruction", ["make indicator beautiful", "change unknown to red", "do not change indicator to red", "change indicator to red and blue", "change indicator to red and erase background", "change indicator to red; erase background"])
def test_ambiguous_or_unknown_instructions_fail_closed(instruction):
    with pytest.raises(ValueError):
        interpret(instruction, catalog())


def test_shape_quality_detects_landmark_drift_and_silhouette_loss(tmp_path):
    create(tmp_path)
    image = Image.open(tmp_path / "robot.png").convert("RGBA")
    spec = {"silhouette": {"selector": {"kind": "background", "rgb": [245, 242, 235]}, "min_iou": 1, "max_hausdorff": 0}, "landmarks": {"indicator": {"selector": catalog()["regions"]["indicator"]["selector"], "expected": [256, 392], "tolerance": 0}}}
    assert assess(image, image, spec)["pass"]
    shifted = Image.fromarray(np.roll(np.array(image), 2, axis=1))
    assert not assess(image, shifted, spec)["pass"]


def test_retry_changes_only_a_cause_specific_parameter_and_stops(tmp_path):
    create(tmp_path)
    spec = plan("change indicator to red", catalog(), tmp_path, tmp_path / "plan")
    spec.update(mode="inpaint", parameters={"seed": 1}, quality={"min_changed_pixels": 1})
    class Backend:
        calls = []
        def generate(self, image, mask, parameters, directory):
            self.calls.append(parameters["seed"])
            return image if parameters["seed"] == 1 else Image.new("RGBA", image.size, "red")
    backend = Backend()
    directory, report = run_trials(spec, tmp_path / "runs", {"max_attempts": 3, "changes": [{"cause": "no_change", "parameters": {"seed": 2}}]}, backend)
    assert backend.calls == [1, 2]
    assert report["attempts"][0]["cause"] == "no_change"
    assert report["status"] == "needs_visual_review"
    assert report["best_candidate"] == report["attempts"][1]["directory"]
    assert (directory / "trials.json").exists()
    assert len(collect(directory)["records"]) == 2


def test_retry_cannot_expand_masks_or_repeat_identical_conditions(tmp_path):
    create(tmp_path)
    spec = plan("change indicator to red", catalog(), tmp_path, tmp_path / "plan")
    with pytest.raises(ValueError):
        run_trials(spec, tmp_path, {"max_attempts": 2, "changes": [{"cause": "shape_drift", "parameters": {"editable_mask": "other.png"}}]})
    spec.update(mode="inpaint", parameters={"seed": 1}, quality={"min_changed_pixels": 1})
    class Noop:
        def generate(self, image, mask, parameters, directory):
            return image
    _, report = run_trials(spec, tmp_path, {"max_attempts": 8, "changes": [{"cause": "no_change", "parameters": {"seed": 1}}]}, Noop())
    assert len(report["attempts"]) == 1


def test_controlnet_compatibility_and_sdxl_workflow():
    p = {"loader": "diffusers", "model_path": "sdxl-inpaint", "family": "sdxl", "prompt": "linen"}
    graph = workflow("a.png", "m.png", p)
    assert graph["1"]["class_type"] == "DiffusersLoader"
    p["controlnet"] = {"family": "sd15", "model": "canny.safetensors", "image": "edge.png"}
    with pytest.raises(ValueError, match="families"):
        workflow("a.png", "m.png", p)
    p["family"] = "sd15"
    graph = workflow("a.png", "m.png", p)
    assert graph["7"]["inputs"]["positive"] == ["12", 0]


def test_multiview_measures_shared_heights_and_reports_unknown_depth(tmp_path):
    create(tmp_path)
    view = {"image": "robot.png", "projection": "orthographic", "pixels_per_unit": 100, "origin": [256, 470], "landmarks": {"top": {"selector": {"kind": "background", "rgb": [245, 242, 235]}, "measure": "top"}}}
    spec = {"views": {"front": view, "back": copy.deepcopy(view)}, "alignments": [{"landmark": "top", "axis": "y", "views": ["front", "back"], "tolerance": 0}], "feature_views": {"head": ["front", "back"]}}
    report = validate_views(spec, tmp_path)
    assert report["pass"] and report["unverified"]
    spec["views"]["back"]["origin"][1] += 10
    assert not validate_views(spec, tmp_path)["pass"]
    spec["views"]["back"]["origin"][1] -= 10
    spec["visibility"] = [{"view": "back", "feature": "front_only_indicator", "selector": {"kind": "color", "rgb": [51, 153, 221]}, "visible": False}]
    # This intentionally uses the front image as a bogus back view.
    assert not validate_views(spec, tmp_path)["visibility"][0]["pass"]
    assert impact(spec, "head", "front")["views"] == ["back"]
    assert impact(spec, "unknown", "front")["status"] == "unknown"


def test_batch_keeps_per_design_failures_and_does_not_promote(tmp_path):
    create(tmp_path)
    (tmp_path / "catalog.json").write_text(json.dumps(catalog()))
    _, report = execute_batch({"instruction": "change indicator to red", "items": [{"catalog": "catalog.json"}, {"catalog": "missing.json"}]}, tmp_path, tmp_path / "runs")
    assert report["results"][0]["status"] == "needs_visual_review"
    assert report["results"][1]["status"] == "failed"
    assert not report["pass"] and not report["automatic_adoption"]


def test_new_generation_is_separate_and_multi_view(tmp_path):
    spec = {"size": [64, 64], "background": [255, 255, 255, 255], "palette": {"body": [100, 150, 200, 255]}, "parts": [{"shape": "rectangle", "color": "body", "views": {"front": [16, 16, 48, 56], "left": [24, 16, 40, 56], "right": [24, 16, 40, 56], "back": [16, 16, 48, 56]}}]}
    directory, report = generate(spec, tmp_path)
    assert len(report["views"]) == 4
    assert not report["source_preservation_claim"]
    assert Image.open(directory / "views.png").size == (256, 64)


def test_comparison_preserves_conditions_and_never_changes_default(tmp_path):
    create(tmp_path)
    spec = plan("change indicator to red", catalog(), tmp_path, tmp_path / "plan")
    spec.update(mode="inpaint", parameters={"prompt": "red", "seed": 42})
    class Fake:
        def generate(self, image, mask, parameters, directory):
            assert parameters["prompt"] == "red" and parameters["seed"] == 42
            return Image.new("RGBA", image.size, "red")
    _, report = compare(spec, [{"name": "a", "parameters": {"checkpoint": "a.ckpt"}}, {"name": "b", "parameters": {"checkpoint": "b.ckpt"}}], tmp_path / "runs", Fake())
    assert len(report["records"]) == 2 and not report["default_model_changed"]
    with pytest.raises(ValueError):
        compare(spec, [{"name": "bad", "parameters": {"prompt": "different task"}}], tmp_path / "runs", Fake())


def test_verified_recipe_rejects_unreviewed_or_different_permission_boundary(tmp_path):
    from design_editor.pipeline import run
    from design_editor.review import record_review
    from design_editor.recipes import verified_recipe, apply_recipe
    create(tmp_path)
    spec = plan("change indicator to red", catalog(), tmp_path, tmp_path / "plan")
    directory, report = run(spec, tmp_path / "runs")
    with pytest.raises(ValueError, match="acceptance review"):
        verified_recipe(directory)
    record_review(directory, "accepted", "test", "indicator only", report["result_sha256"])
    recipe = verified_recipe(directory)
    assert apply_recipe(spec, recipe)["recipe_evidence"] == report["result_sha256"]
    changed = copy.deepcopy(spec)
    changed["hue"] = 60
    with pytest.raises(ValueError):
        apply_recipe(changed, recipe)
    Image.new("L", (512, 512), 255).save(tmp_path / "different.png")
    changed = dict(spec, editable_mask=str(tmp_path / "different.png"))
    with pytest.raises(ValueError):
        apply_recipe(changed, recipe)


def test_edge_preservation_fails_when_reference_shape_disappears():
    a = Image.new("RGBA", (32, 32), "white")
    from PIL import ImageDraw
    ImageDraw.Draw(a).ellipse((8, 8, 23, 23), fill="blue")
    quality = {"edge_preservation": {"box": [0, 0, 32, 32], "max_mean_distance": 0}}
    assert assess(a, a, quality)["pass"]
    assert not assess(a, Image.new("RGBA", (32, 32), "white"), quality)["pass"]


def test_boundary_measurement_detects_a_new_seam_without_claiming_intent():
    from design_editor.quality import boundary_metrics
    image = Image.new("RGBA", (16, 16), "white")
    mask = np.zeros((16, 16), np.uint8)
    mask[4:12, 4:12] = 255
    pixels = np.array(image)
    pixels[4:12, 4:12, :3] = 0
    measured = boundary_metrics(image, Image.fromarray(pixels), mask)
    assert measured["reference_mean_rgb_jump"] == 0
    assert measured["result_mean_rgb_jump"] == 255


def test_disappeared_foreground_is_a_shape_failure_not_an_unhandled_error():
    original = Image.new("RGBA", (16, 16), "white")
    from PIL import ImageDraw
    ImageDraw.Draw(original).rectangle((4, 4, 10, 10), fill="blue")
    report = assess(original, Image.new("RGBA", (16, 16), "white"), {"silhouette": {"selector": {"kind": "background", "rgb": [255, 255, 255]}}})
    assert not report["pass"] and report["checks"][0]["kind"] == "silhouette"


def test_retries_detect_external_mask_mutation(tmp_path):
    create(tmp_path)
    spec = plan("change indicator to red", catalog(), tmp_path, tmp_path / "plan")
    spec.update(mode="inpaint", parameters={"seed": 1})
    class Mutating:
        calls = 0
        def generate(self, image, mask, parameters, directory):
            self.calls += 1
            Image.new("L", image.size, 255).save(spec["editable_mask"])
            return image
    backend = Mutating()
    _, report = run_trials(spec, tmp_path / "runs", {"max_attempts": 2, "changes": [{"cause": "no_change", "parameters": {"seed": 2}}]}, backend)
    assert backend.calls == 1
    assert report["status"] == "failed"
    assert "permission masks changed" in report["attempts"][-1]["reason"]


def test_new_generation_failure_is_retained(tmp_path):
    with pytest.raises(ValueError):
        generate({"size": [32, 32]}, tmp_path)
    assert len(list(tmp_path.glob("*/failure.json"))) == 1


def test_generation_review_binds_every_view_and_history(tmp_path):
    from design_editor.review import record_review
    spec = {"size": [64, 64], "background": [255, 255, 255, 255], "palette": {"body": [100, 150, 200, 255]}, "parts": [{"shape": "rectangle", "color": "body", "views": {"front": [16, 16, 48, 56]}}]}
    directory, report = generate(spec, tmp_path)
    record_review(directory, "accepted", "test", "declared rectangular views checked", report["sheet_sha256"])
    assert collect(tmp_path)["records"][0]["review_statuses"] == ["accepted"]
    Image.new("RGBA", (64, 64), "red").save(directory / "front.png")
    with pytest.raises(ValueError, match="hashes"):
        record_review(directory, "accepted", "test", "tampered", report["sheet_sha256"])
