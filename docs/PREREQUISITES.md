# Prerequisites and their licences

This project is GPL-3.0. Nothing below is part of it except what the installer bundles (Python). Checked
2026-11-25; check the linked pages for current terms.

| Item | Needed? | Licence | Open source | Where |
|---|---|---|---|---|
| Krita (Krita Foundation / KDE) | yes | GPL-3.0. Its plugin API is GPL, so distributed Krita plugins must be GPL too (this one is) | yes | [krita.org](https://krita.org/en/download/) |
| Claude Code (Anthropic), or any MCP client | yes | proprietary | no | [claude.com/claude-code](https://claude.com/claude-code) |
| Python (PSF) | bundled by the installer | PSF License v2 (redistribution allowed; the licence file ships inside `python\`) | yes | [python.org](https://www.python.org/downloads/windows/) |
| Inno Setup | only to build the installer | Inno Setup License (free for any use; commercial users are asked to buy a licence) | source available | [jrsoftware.org](https://jrsoftware.org/isinfo.php) |

## Optional AI tools

| Item | Licence | Where |
|---|---|---|
| PyTorch | BSD-3-Clause | [pytorch.org](https://pytorch.org) |
| transformers, huggingface_hub (Hugging Face) | Apache-2.0 | PyPI |
| numpy, Pillow, OpenCV, timm, einops, kornia | BSD / MIT-CMU / Apache-2.0 | PyPI |
| Grounding DINO base (IDEA-Research) | Apache-2.0 | [model card](https://huggingface.co/IDEA-Research/grounding-dino-base) |
| SAM 2.1 hiera-large (Meta) | Apache-2.0 | [model card](https://huggingface.co/facebook/sam2.1-hiera-large) |
| BiRefNet (ZhengPeng7) | MIT | [model card](https://huggingface.co/ZhengPeng7/BiRefNet) |
| LaMa (advimman) | Apache-2.0 | [github.com/advimman/lama](https://github.com/advimman/lama) |
| `big-lama.pt` TorchScript export (enesmsahin/simple-lama-inpainting) | Apache-2.0 (repository licence) | [release v0.1.0](https://github.com/enesmsahin/simple-lama-inpainting/releases/tag/v0.1.0) |

All the model licences allow commercial use. Model weights are downloaded by `ai_tools/get_models.py` straight
from the sources above; this project doesn't host or redistribute them.
