"""Download the AI models for the optional cut-out tools and print each one's licence.

  python get_models.py [MODELS_DIR]

Default folder: %LOCALAPPDATA%\\claude-krita-bridge\\models (about 2.4 GB). Run it with the Python of the
environment you made for the AI tools (see README.md). The models come from their own authors' pages; they are
not part of this project and each keeps its own licence:
  Grounding DINO base  (IDEA-Research)  Apache-2.0
  SAM 2.1 hiera-large  (Meta)           Apache-2.0
  BiRefNet             (ZhengPeng7)     MIT
  LaMa big-lama.pt     (advimman/lama, TorchScript export by enesmsahin/simple-lama-inpainting)  Apache-2.0
"""
import os
import sys
import urllib.request

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "claude-krita-bridge", "models")
os.makedirs(ROOT, exist_ok=True)
os.environ.setdefault("HF_HOME", os.path.join(ROOT, "hf"))
from huggingface_hub import HfApi, snapshot_download  # noqa: E402

REPOS = {
    "grounding-dino-base": "IDEA-Research/grounding-dino-base",     # find objects by name
    "sam2.1-hiera-large": "facebook/sam2.1-hiera-large",            # exact mask for a box
    "BiRefNet": "ZhengPeng7/BiRefNet",                              # high-quality edges (hair etc.)
}
api = HfApi()
for local, repo in REPOS.items():
    info = api.model_info(repo)
    lic = (info.card_data or {}).get("license") if info.card_data else None
    print(f"{repo}: licence {lic}", flush=True)
    snapshot_download(repo, local_dir=os.path.join(ROOT, local),
                      allow_patterns=["*.json", "*.safetensors", "*.py", "*.txt", "*.md"])

lama = os.path.join(ROOT, "big-lama.pt")
if not os.path.exists(lama):
    print("advimman/lama big-lama.pt: licence apache-2.0", flush=True)
    urllib.request.urlretrieve("https://github.com/enesmsahin/simple-lama-inpainting/releases/download/v0.1.0/big-lama.pt", lama)
print("big-lama.pt", os.path.getsize(lama) // 2**20, "MB")
print("models are in", ROOT)
