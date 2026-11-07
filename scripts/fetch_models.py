"""Download optional official comparison weights; never redistribute them in Git."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import requests

try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass


def fetch(root, family):
    if family == "sdxl":
        repo, revision = "diffusers/stable-diffusion-xl-1.0-inpainting-0.1", "115134f363124c53c7d878647567d04daf26e41e"
        base = root / "models/diffusers/sdxl-inpaint"
    else:
        repo, revision = "lllyasviel/control_v11p_sd15_canny", "115a470d547982438f70198e353a921996e2e819"
        base = root / "models/controlnet"
    response = requests.get(f"https://huggingface.co/api/models/{repo}/revision/{revision}?blobs=true", timeout=30)
    response.raise_for_status()
    metadata = response.json()
    records = []
    for file in metadata["siblings"]:
        name = file["rfilename"]
        if family == "sdxl":
            wanted = name.endswith((".json", ".txt", ".fp16.safetensors")) and name not in ("README.md", ".gitattributes")
            destination = base / name
        else:
            wanted = name == "diffusion_pytorch_model.fp16.safetensors"
            destination = base / "sd15-canny-fp16.safetensors"
        if not wanted:
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        expected = file.get("lfs", {}).get("sha256")
        def sha(path):
            with path.open("rb") as stream:
                return hashlib.file_digest(stream, "sha256").hexdigest()
        valid = destination.exists() and (sha(destination) == expected if expected else destination.stat().st_size == file.get("size"))
        if not valid:
            url = f"https://huggingface.co/{repo}/resolve/{revision}/{name}?download=true"
            subprocess.run(["curl.exe" if __import__("os").name == "nt" else "curl", "--fail", "--location", "--continue-at", "-", "--retry", "3", "--retry-all-errors", "--speed-time", "30", "--speed-limit", "1024", "--output", str(destination), url], check=True)
        actual = sha(destination)
        if expected and actual != expected:
            raise ValueError("Model hash mismatch: " + name)
        records.append({"file": str(destination.relative_to(root)).replace("\\", "/"), "sha256": actual, "size_bytes": destination.stat().st_size})
    manifest = {"repository": repo, "revision": revision, "family": family, "files": records}
    (root / (family + "-manifest.json")).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"family": family, "files": len(records), "bytes": sum(r["size_bytes"] for r in records)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("family", choices=("sdxl", "controlnet"))
    parser.add_argument("--comfy-root", type=Path, default=Path(".runtime/ComfyUI"))
    args = parser.parse_args()
    fetch(args.comfy_root, args.family)
