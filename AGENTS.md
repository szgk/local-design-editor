# Agent workflow

This repository provides a local CLI, not a paid image service. Phase 1 verification gates passed before Phase 2/3 implementation. Use the declared acceptance tasks in docs/phases.md; implementation coverage does not imply arbitrary-image quality guarantees.

1. Read the current request and approved source. Separate the requested edit from protected constraints. Do not treat the latest generated candidate as approved.
2. Choose exact crop for extraction and deterministic recolor for color-only edits. For explicit flat geometric changes use `geometry` with a declared background and coordinates, or `composite` with an authored patch. Use local masked inpainting only when the requested content needs synthesis. Never treat a failed diffusion attempt on an exact geometric task as evidence that a larger model is required.
3. Create the smallest appropriate editable mask. Protected masks override it. Keep source pixels and coordinates immutable; never resize to hide a mismatch.
4. Run a request with `design-edit run <request.json>`. Keep all run artifacts local; they may contain private images and paths.
5. Inspect `validation.json` and `comparison.png`. Zero protected RGBA differences is necessary. It does not prove the desired edit happened. Review the edited region at native resolution and enlarged, including boundaries and unintended shape changes.
6. Record human review separately. Do not claim unmeasured landmarks, multi-view consistency, or 3D structure are verified.
7. On failure, preserve evidence and classify the cause. Do not retry with identical conditions indefinitely or automatically adopt a failed candidate.
8. Auto instructions use an explicit region catalog and a bounded bilingual grammar. Reject unsupported qualifiers, unknown targets and multiple operations. Do not silently guess a target or add model prompts.
9. Compare models with the same source, mask, prompt, seed and sampling conditions. Keep failing candidates and visual review separate from exact-pixel checks. Never promote a larger model without demonstrated improvement.
10. Verify observable cross-view coordinates only after declaring projection, scale, origin and object-relative sides. Hidden geometry remains unknown. Return impacted-view review candidates; do not regenerate other views automatically.

Run `python -m pytest -q` after changes. Use generic, independently created public fixtures. Do not commit local run histories, personal paths, private artwork, model weights, credentials, or references that identify private projects. Check tracked files before publication.
