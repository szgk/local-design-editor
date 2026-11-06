"""Core-node SD1.5 inpainting backend. No paid or remote API."""
import io
import time
import uuid
from typing import Protocol
from urllib.parse import urlparse

import requests
from PIL import Image


class Backend(Protocol):
    def generate(self, image, mask, parameters, directory): ...


def workflow(image_name, mask_name, p):
    def node(kind, **inputs):
        return {"class_type": kind, "inputs": inputs}
    return {
        "1": node("CheckpointLoaderSimple", ckpt_name=p["checkpoint"]),
        "2": node("LoadImage", image=image_name),
        "3": node("LoadImageMask", image=mask_name, channel="red"),
        "4": node("CLIPTextEncode", text=p["prompt"], clip=["1", 1]),
        "5": node("CLIPTextEncode", text=p.get("negative_prompt", ""), clip=["1", 1]),
        "6": node("InpaintModelConditioning", positive=["4", 0], negative=["5", 0], vae=["1", 2], pixels=["2", 0], mask=["3", 0], noise_mask=True),
        "7": node("KSampler", model=["1", 0], positive=["6", 0], negative=["6", 1], latent_image=["6", 2], seed=p.get("seed", 1), steps=p.get("steps", 20), cfg=p.get("cfg", 6.0), sampler_name="euler", scheduler="normal", denoise=p.get("denoise", 0.8)),
        "8": node("VAEDecode", samples=["7", 0], vae=["1", 2]),
        "9": node("SaveImage", images=["8", 0], filename_prefix="design_editor"),
    }


class ComfyBackend:
    def __init__(self, url="http://127.0.0.1:8188", timeout=300):
        parsed = urlparse(url)
        if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1") or parsed.username:
            raise ValueError("Only local HTTP ComfyUI is supported")
        self.url, self.timeout = url.rstrip("/"), timeout
        self.session = requests.Session()
        self.session.trust_env = False

    def request(self, method, path, **kwargs):
        response = self.session.request(method, self.url + path, timeout=30, **kwargs)
        response.raise_for_status()
        return response

    def upload(self, image):
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        info = self.request("POST", "/upload/image", files={"image": (uuid.uuid4().hex + ".png", stream.getvalue(), "image/png")}, data={"type": "input", "overwrite": "false"}).json()
        return "/".join(filter(None, (info.get("subfolder"), info["name"])))

    def generate(self, image, mask, parameters, directory):
        import json
        original = image
        context_box = parameters.get("context_box")
        if context_box:
            from .imaging import crop
            image = crop(image, context_box)
            # Every editable pixel must be contained in this crop.
            import numpy as np
            outside = np.array(Image.new("L", original.size))
            x0, y0, x1, y1 = context_box
            outside[y0:y1, x0:x1] = 1
            if np.any((np.array(mask) > 0) & (outside == 0)):
                raise ValueError("Context box must contain the entire editable mask")
            if x1 - x0 != y1 - y0:
                raise ValueError("Context box must be square to avoid aspect distortion")
            mask = crop(mask, context_box)
            target = parameters.get("context_resolution", 512)
            if not isinstance(target, int) or not 64 <= target <= 1024:
                raise ValueError("Context resolution must be 64..1024")
            image = image.resize((target, target), Image.Resampling.LANCZOS)
            mask = mask.resize((target, target), Image.Resampling.NEAREST)
        # Pad to latent grid; crop back without rescaling the source coordinates.
        size = ((image.width + 7) // 8 * 8, (image.height + 7) // 8 * 8)
        canvas = Image.new("RGB", size, "white")
        canvas.paste(image.convert("RGB"))
        padded_mask = Image.new("L", size)
        padded_mask.paste(mask)
        graph = workflow(self.upload(canvas), self.upload(padded_mask), parameters)
        (directory / "workflow.json").write_text(json.dumps(graph, indent=2), encoding="utf-8")
        stats = self.request("GET", "/system_stats").json()
        (directory / "backend.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
        info = self.request("POST", "/prompt", json={"prompt": graph, "client_id": uuid.uuid4().hex}).json()
        prompt_id = info["prompt_id"]
        (directory / "prompt_id.txt").write_text(prompt_id, encoding="utf-8")
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            history = self.request("GET", "/history/" + prompt_id).json().get(prompt_id)
            if history:
                (directory / "history.json").write_text(json.dumps(history, indent=2), encoding="utf-8")
                if history.get("status", {}).get("status_str") == "error":
                    raise RuntimeError("ComfyUI execution failed; see history.json")
                images = history.get("outputs", {}).get("9", {}).get("images", [])
                if images:
                    response = self.request("GET", "/view", params=images[0])
                    with Image.open(io.BytesIO(response.content)) as result:
                        if result.size != size:
                            raise ValueError("Backend changed canvas dimensions")
                        result = result.convert("RGBA").crop((0, 0, image.width, image.height))
                        if context_box:
                            patch = result.resize((x1 - x0, y1 - y0), Image.Resampling.LANCZOS)
                            result = original.copy()
                            result.paste(patch, (x0, y0))
                        result.putalpha(original.getchannel("A"))
                        return result
            time.sleep(0.5)
        raise TimeoutError("ComfyUI deadline exceeded; job may still be queued/running. See prompt_id.txt; no automatic retry.")
