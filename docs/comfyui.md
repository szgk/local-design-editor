# ComfyUI local setup

Use a dedicated Python environment and the official source. Runtime files and model weights belong outside Git (`.runtime/` is ignored). No custom nodes are required.

Test baseline: Python 3.12, RTX 5060 8 GB; PyTorch 2.10.0 with CUDA 12.8 wheels. Choose a compatible CUDA wheel for your GPU. CPU execution is possible but slower. Do not install unrelated models for Phase 1.

```sh
git clone https://github.com/Comfy-Org/ComfyUI.git .runtime/ComfyUI
git -C .runtime/ComfyUI checkout c85957ad7f0b7b963931ff3ca6b57816d433c869
python -m pip install torch==2.10.0 torchvision==0.25.0 --index-url https://download.pytorch.org/whl/cu128
python -m pip install -r .runtime/ComfyUI/requirements.txt
```

Application dependencies are pinned in `requirements.lock`. The tested Windows GPU environment is captured in `runtime-windows.lock`. To reproduce it, install PyTorch from the CUDA index above, then `python -m pip install -r runtime-windows.lock`. This is a Windows snapshot, not a portable GPU lock. ComfyUI's upstream requirements include unpinned dependencies, so the source checkout alone is not a complete environment lock.

Download the [SD1.5 Inpainting checkpoint](https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-inpainting/blob/main/sd-v1-5-inpainting.ckpt) to `.runtime/ComfyUI/models/checkpoints/sd-v1-5-inpainting.ckpt`. Model revision: `8a4288a76071f7280aedbdb3253bdb9e9d5d84bb`. This model uses CreativeML OpenRAIL-M; consult its model card and license. The download is approximately 4.27 GB. Weights are not redistributed here.

Verified checkpoint SHA256: `c6bbc15e3224e6973459ba78de4998b80b50112b0ae5b5c67113d56b4e366b19`.

```sh
python .runtime/ComfyUI/main.py --listen 127.0.0.1 --port 8188 --lowvram --disable-all-custom-nodes
design-edit run examples/inpaint.json
```

Use a separate terminal for the server. A low-VRAM setting is a starting configuration, not a guarantee of memory usage. Record the exact model hash, runtime revision, GPU and time for comparisons. The client permits only loopback HTTP and disables environment HTTP proxies for image traffic.

The workflow is assembled by `design_editor/comfy.py` and saved with each run. It uses `CheckpointLoaderSimple`, `LoadImage`, `LoadImageMask` (red channel, white=editable), `CLIPTextEncode`, `InpaintModelConditioning`, `KSampler`, `VAEDecode`, `SaveImage`. It never trusts the diffusion output to preserve pixels: the final application-side composite supplies that boundary.

For small targets, optional `parameters.context_box` selects a square context crop in source coordinates, containing the whole effective mask. `context_resolution` (64–1024, default 512) scales only this working crop for inference. The candidate patch is resized back to the crop dimensions, then composited within the original mask. This changes interpolation inside the edit region; it does not create new evidence or guarantee shape accuracy. The full source and protected pixels are never resized. Non-square crops are rejected to avoid aspect distortion.
