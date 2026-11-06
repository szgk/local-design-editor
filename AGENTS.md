# Agent workflow

This repository provides a local CLI, not a paid image service. Keep changes within Phase 1 until its verification gates pass.

1. Read the current request and approved source. Separate the requested edit from protected constraints. Do not treat the latest generated candidate as approved.
2. Choose exact crop for extraction, deterministic recolor for color-only edits, and local masked inpainting for shape changes. Never route extraction or recolor through a generative backend.
3. Create the smallest appropriate editable mask. Protected masks override it. Keep source pixels and coordinates immutable; never resize to hide a mismatch.
4. Run a request with `design-edit run <request.json>`. Keep all run artifacts local; they may contain private images and paths.
5. Inspect `validation.json` and `comparison.png`. Zero protected RGBA differences is necessary. It does not prove the desired edit happened. Review the edited region at native resolution and enlarged, including boundaries and unintended shape changes.
6. Record human review separately. Do not claim unmeasured landmarks, multi-view consistency, or 3D structure are verified.
7. On failure, preserve evidence and classify the cause. Do not retry with identical conditions indefinitely or automatically adopt a failed candidate.

Run `python -m pytest -q` after changes. Use generic, independently created public fixtures. Do not commit local run histories, personal paths, private artwork, model weights, credentials, or references that identify private projects. Check tracked files before publication.
