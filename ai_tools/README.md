# Optional AI tools: cut out, remove, match

These power `krita_cutout`, `krita_remove` and `krita_match`. They're **optional**: the rest of the bridge works
without them. Everything runs locally on your own GPU (or slowly on the CPU), and nothing is sent anywhere.

| Model | Licence | Job |
|---|---|---|
| [Grounding DINO base](https://huggingface.co/IDEA-Research/grounding-dino-base) | Apache-2.0 | finds objects by **name** ("dog", "lamp, chair") |
| [SAM 2.1 hiera-large](https://huggingface.co/facebook/sam2.1-hiera-large) | Apache-2.0 | exact mask from the box |
| [BiRefNet](https://huggingface.co/ZhengPeng7/BiRefNet) | MIT | clean soft edges (hair, fur, fabric), kept inside SAM's area |
| [LaMa](https://github.com/advimman/lama) (`big-lama.pt` TorchScript export from [simple-lama-inpainting](https://github.com/enesmsahin/simple-lama-inpainting)) | Apache-2.0 | content-aware fill for removing things |

The models are about 2.4 GB. They're downloaded from their authors' pages by `get_models.py`, aren't part of this
project, and keep their own licences.

## Set up (about 15 minutes plus downloads)

1. Make a Python environment with PyTorch for your GPU. Follow [pytorch.org](https://pytorch.org/get-started/locally/):
   CUDA for NVIDIA, ROCm for AMD where supported, or CPU.
   ```powershell
   python -m venv "$env:LOCALAPPDATA\claude-krita-bridge\ai-venv"
   & "$env:LOCALAPPDATA\claude-krita-bridge\ai-venv\Scripts\python.exe" -m pip install torch torchvision --index-url <the URL pytorch.org gives you>
   & "$env:LOCALAPPDATA\claude-krita-bridge\ai-venv\Scripts\python.exe" -m pip install -r ai_tools\requirements.txt
   ```
2. Download the models (about 2.4 GB):
   ```powershell
   & "$env:LOCALAPPDATA\claude-krita-bridge\ai-venv\Scripts\python.exe" ai_tools\get_models.py
   ```
3. Tell the bridge where that Python is, in `%APPDATA%\claude-krita-bridge\config.json`:
   ```json
   { "ai": { "python": "%LOCALAPPDATA%\\claude-krita-bridge\\ai-venv\\Scripts\\python.exe" } }
   ```
   Models in another folder? Add `"models_dir"`. Pin a GPU or limit threads with `"env"`, e.g.
   `{"HIP_VISIBLE_DEVICES": "0"}` (AMD) or `{"CUDA_VISIBLE_DEVICES": "0"}` (NVIDIA).

## Use without Krita

```powershell
python ai_tools\cutout.py cut    photo.jpg --what "dog, ball" [--merge] [--pick 2] [--all] [--box x0,y0,x1,y1]
python ai_tools\cutout.py remove photo.jpg --what "man in the background" [--pick 2] | --mask mask.png
python ai_tools\cutout.py match  cutout.png scene.jpg [--region x0,y0,x1,y1] [--strength 0.5] [--shadow]
```

## Tips and limits
- Every search writes `<image>_found.jpg` with each match **numbered**. A name search can grab the wrong object
  (a small figure in the background, say), so check the preview and re-run with `pick`.
- `merge` joins several matches into one piece (a person and what they hold).
- LaMa is for **small and medium** objects; very large holes come out smeary.
- Very grainy photos cut better after a light denoise.
- A run takes about a minute, mostly model loading. The models are loaded fresh each call to keep memory free.
- Memory: about 6-8 GB of VRAM is comfortable for the large SAM model at once; less works more slowly.
