# Validation record

Phase 1 development record. Synthetic tests establish the pixel preservation boundary; they do not establish general character editing quality.

- Automated tests: 11 passed on Python 3.12 (Windows).
- Generic robot recolor: 1,073 editable pixels changed; zero protected RGBA differences; 512×512 preserved; source SHA256 unchanged.
- Extract: exact 288×276 crop; source unchanged.
- Diffusion backend: real SD1.5 Inpainting inference through local ComfyUI succeeded on RTX 5060 (8 GB), Python 3.12.15, PyTorch 2.10.0+cu128, ComfyUI 0.44.0, pinned source revision recorded in setup. Warm end-to-end request approximately 2.8 seconds; cold first request approximately 7.6 seconds. These are observations, not benchmarks.
- Inpainting removal task: circular indicator removed; 4,225 editable pixels changed; zero protected RGBA differences; 512×512 retained. Visually reviewed at native size. A slight panel-tone transition remains inside the permitted region; not a universal seamlessness guarantee.
- Square replacement task: FAILED visual intent review. Whole-image inference erased the indicator. Context-crop trials produced a ring or a bordered square with an unwanted center mark. A later seed produced an irregular two-color shape. Protected pixels remained exact in all these trials. The pipeline does not mark these candidates accepted or modify defaults based on this result.
- Recolor: visually reviewed; only indicator color changed. Extract: crop dimensions and source immutability verified.
- Run reports intentionally retain `intent_review: pending`. This document records the separate visual assessment; the application never silently promotes automatic pixel checks into design approval.

![Recolor: source, result, difference](../examples/recolor-comparison.png)

![Inpainting removal: source, result, difference](../examples/inpaint-comparison.png)

![Partial square attempt: source, result, difference](../examples/square-partial-comparison.png)

Phase 1 infrastructure and preservation tests are operational. Arbitrary shape-edit quality is not accepted as complete. No ControlNet, SDXL, other generation model or paid API was introduced. Improve masks/context and compare fixed prompts before expanding model dependencies. Exact geometric shapes can be authored deterministically and passed through `composite`; diffusion is not needed for that case.

The model SHA256 and runtime source revision are in [setup](comfyui.md). Runtime API reported approximately 3.2 GiB occupied device VRAM after inference (includes desktop and other allocations); peak process VRAM was not measured and is not claimed.

CI runs the CPU test suite on Windows and Linux with Python 3.11/3.12. GPU tests are manual and must be recorded separately. No private artwork is included.
