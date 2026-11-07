"""Repeatable comparisons; metrics never replace independent visual assessment."""
import copy
import json
from pathlib import Path
import subprocess
import threading
import time
import uuid

from .pipeline import run, digest


def compare(spec, profiles, root="runs", backend=None):
    if not profiles:
        raise ValueError("At least one model profile is required")
    directory = Path(root) / ("comparison-" + uuid.uuid4().hex)
    directory.mkdir(parents=True, exist_ok=False)
    records = []
    for profile in profiles:
        request = copy.deepcopy(spec)
        # These are architecture/execution settings, not different editing instructions.
        allowed = {"family", "loader", "checkpoint", "model_path", "controlnet"}
        if not profile["parameters"].keys() <= allowed:
            raise ValueError("Comparison profiles must not change prompt, seed or sampling conditions")
        request.setdefault("parameters", {}).update(profile["parameters"])
        stop, samples = threading.Event(), []
        def monitor():
            while not stop.is_set():
                try:
                    flags = {"creationflags": 0x08000000} if __import__("os").name == "nt" else {}
                    value = subprocess.check_output(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], timeout=5, **flags)
                    samples.append(int(value.decode().splitlines()[0]))
                except (OSError, subprocess.SubprocessError, ValueError):
                    pass
                stop.wait(0.25)
        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()
        started = time.monotonic()
        try:
            child, report = run(request, directory, backend)
            record = {"name": profile["name"], "directory": child.name, "parameters": profile["parameters"], "report": report, "status": report["overall_status"], "model_identity": profile.get("identity", "not supplied")}
        except Exception as error:
            record = {"name": profile["name"], "status": "failed", "error": str(error)}
        finally:
            stop.set()
            thread.join(timeout=6)
        record.update(elapsed_seconds=time.monotonic() - started, sampled_device_peak_mib=max(samples) if samples else None, vram_measurement="sampled whole-device usage, includes desktop and other processes; not exact allocator peak", intent_review="pending")
        records.append(record)
    summary = {"source_sha256": digest(spec["source"]), "editable_mask_sha256": digest(spec["editable_mask"]), "common_parameters": spec["parameters"], "records": records, "default_model_changed": False}
    (directory / "comparison.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return directory, summary
