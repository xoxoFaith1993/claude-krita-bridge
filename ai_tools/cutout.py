"""cutout - Photoshop-style AI selection, cut-out, object removal and blending (GPU via PyTorch, CPU works too).

  python cutout.py cut    IMAGE --what "dog, ball" [--merge] [--pick 2] [--all] [--box x0,y0,x1,y1] [--out DIR]
                    (every match is numbered on <name>_found.jpg; --pick chooses, --merge joins them into one piece)
  python cutout.py remove IMAGE --what "the man in the background"  |  --mask MASK.png        [--out DIR]
  python cutout.py match  CUTOUT.png TARGET.jpg [--region x0,y0,x1,y1] [--strength 0.5] [--shadow] [--out DIR]

Folders: CUTOUT_MODELS (models, from get_models.py) and CUTOUT_OUT (results); the Krita bridge sets both.
GPU: any PyTorch build works - CUDA (NVIDIA), ROCm (AMD) or CPU (slow).

cut:    Grounding DINO finds the object by name -> SAM 2.1 draws its exact mask -> BiRefNet refines the edge
        (hair, fur, fuzzy outlines) inside SAM's area. Writes <name>_cutout.png (transparent, cropped), _mask.png
        (white = object, full size) and a JSON line with the box, so the cutout can go back to the same spot.
remove: LaMa fills the object's area from its surroundings (content-aware fill). Writes <name>_removed.png.
match:  shifts the cutout's colour and brightness toward the target (or a region of it) so it sits in the scene,
        optionally with a soft drop shadow. Writes <name>_matched.png.
Licences: Grounding DINO Apache-2.0, SAM 2.1 Apache-2.0, BiRefNet MIT, LaMa Apache-2.0.
"""
import argparse, json, os, sys, time
from pathlib import Path

_DATA = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "claude-krita-bridge"
MODELS = Path(os.environ.get("CUTOUT_MODELS") or _DATA / "models")
OUT = Path(os.environ.get("CUTOUT_OUT") or _DATA / "work" / "out")
os.environ.setdefault("HF_HOME", str(MODELS / "hf"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")          # models are local; never phone home

import numpy as np
from PIL import Image, ImageFilter
import torch

DEV = "cuda" if torch.cuda.is_available() else "cpu"


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def load_rgb(p):
    return Image.open(p).convert("RGB")


# ------------------------------------------------------------------ find + mask
def find_boxes(img, what, all_=False, pick=None, preview=None):
    """Find objects by name. Several things: separate with commas ("dog, ball"). Every match is numbered
    (best score first) and drawn on `preview`, so the right one can be chosen with pick="2" or "1,3"."""
    from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
    p = MODELS / "grounding-dino-base"
    proc = AutoProcessor.from_pretrained(p)
    model = AutoModelForZeroShotObjectDetection.from_pretrained(p).to(DEV).eval()
    text = ". ".join(t.strip().lower() for t in what.split(",") if t.strip()) + "."
    inputs = proc(images=img, text=text, return_tensors="pt").to(DEV)
    with torch.no_grad():
        out = model(**inputs)
    r = proc.post_process_grounded_object_detection(out, inputs.input_ids, threshold=0.25, text_threshold=0.2,
                                                    target_sizes=[img.size[::-1]])[0]
    labels = r.get("text_labels") or r.get("labels") or [""] * len(r["scores"])
    boxes = [(float(s), [float(v) for v in b], str(l)) for s, b, l in zip(r["scores"], r["boxes"], labels)]
    boxes.sort(key=lambda t: -t[0])
    del model; torch.cuda.empty_cache() if DEV == "cuda" else None
    if not boxes:
        raise SystemExit(f"couldn't find '{what}' in the picture (try other words, or --box)")
    for i, (s, b, l) in enumerate(boxes, 1):
        log(f"  #{i}: {l or what} score {s:.2f} box {[round(v) for v in b]}")
    if preview:
        from PIL import ImageDraw, ImageFont
        pv = img.copy(); d = ImageDraw.Draw(pv); lw = max(3, img.width // 300)
        try:
            font = ImageFont.truetype("arialbd.ttf", max(24, img.width // 30))
        except OSError:
            font = ImageFont.load_default()
        for i, (s, b, l) in enumerate(boxes, 1):
            col = (200, 40, 60) if i == 1 else (255, 210, 0)
            d.rectangle(b, outline=col, width=lw)
            d.text((b[0] + lw * 2, b[1] + lw), f"#{i} {l}", fill=col, font=font, stroke_width=2, stroke_fill=(0, 0, 0))
        pv.thumbnail((1600, 1600)); pv.save(preview, quality=88)
    if pick:
        idx = [int(v) - 1 for v in str(pick).split(",")]
        return [(boxes[i][0], boxes[i][1]) for i in idx if 0 <= i < len(boxes)]
    chosen = boxes if all_ else boxes[:1]
    return [(s, b) for s, b, _ in chosen]


def sam_masks(img, boxes):
    from transformers import Sam2Processor, Sam2Model
    p = MODELS / "sam2.1-hiera-large"
    proc = Sam2Processor.from_pretrained(p)
    model = Sam2Model.from_pretrained(p).to(DEV).eval()
    inputs = proc(images=img, input_boxes=[[b for b in boxes]], return_tensors="pt").to(DEV)
    with torch.no_grad():
        out = model(**inputs, multimask_output=False)
    masks = proc.post_process_masks(out.pred_masks.cpu(), inputs["original_sizes"])[0]   # (n, 1, H, W)
    del model; torch.cuda.empty_cache() if DEV == "cuda" else None
    return [m[0].numpy().astype(np.float32) for m in masks]


def birefnet_refine(img, box, sam):
    """Run BiRefNet on a crop around the object and keep its soft edge only where SAM says the object is."""
    from transformers import AutoModelForImageSegmentation
    W, H = img.size
    x0, y0, x1, y1 = box
    mx, my = (x1 - x0) * 0.15, (y1 - y0) * 0.15
    cx0, cy0, cx1, cy1 = int(max(0, x0 - mx)), int(max(0, y0 - my)), int(min(W, x1 + mx)), int(min(H, y1 + my))
    crop = img.crop((cx0, cy0, cx1, cy1))
    model = AutoModelForImageSegmentation.from_pretrained(MODELS / "BiRefNet", trust_remote_code=True).float().to(DEV).eval()  # weights ship as fp16
    x = np.asarray(crop.resize((1024, 1024), Image.BICUBIC), np.float32) / 255
    x = (x - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]
    t = torch.from_numpy(x.transpose(2, 0, 1)[None].astype(np.float32)).to(DEV)
    with torch.no_grad():
        pred = model(t)[-1].sigmoid()[0, 0].float().cpu().numpy()
    del model; torch.cuda.empty_cache() if DEV == "cuda" else None
    soft = np.asarray(Image.fromarray((pred * 255).astype(np.uint8)).resize(crop.size, Image.BICUBIC), np.float32) / 255
    full = np.zeros((H, W), np.float32); full[cy0:cy1, cx0:cx1] = soft
    # SAM's region, grown a little so BiRefNet's hair/fur edge isn't clipped
    grow = max(3, int(0.02 * max(x1 - x0, y1 - y0)))
    zone = np.asarray(Image.fromarray((sam * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(2 * (grow // 2) + 1)), np.float32) / 255
    refined = full * zone
    # if BiRefNet locked onto something else in the crop, trust SAM instead
    a, b = refined > 0.5, sam > 0.5
    iou = (a & b).sum() / max((a | b).sum(), 1)
    log(f"  BiRefNet vs SAM agreement: {iou:.2f}")
    if iou < 0.6:
        return np.asarray(Image.fromarray((sam * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2)), np.float32) / 255, "sam"
    return refined, "birefnet"


def drop_scraps(alpha, keep=0.03):
    """Remove small disconnected bits (specks, slivers of background) smaller than `keep` x the main object."""
    import cv2
    solid = (alpha > 0.3).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(solid, connectivity=8)
    if n <= 2:
        return alpha
    areas = stats[1:, cv2.CC_STAT_AREA]
    big = areas.max()
    drop = [i + 1 for i, ar in enumerate(areas) if ar < keep * big]
    if not drop:
        return alpha
    gone = np.isin(lab, drop)
    # also clear the faint fringe around dropped bits
    gone = cv2.dilate(gone.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool) & ~np.isin(lab, [i for i in range(1, n) if i not in drop])
    out = alpha.copy(); out[gone] = 0
    log(f"  removed {len(drop)} stray scrap(s)")
    return out


def cmd_cut(a):
    img = load_rgb(a.image)
    out = Path(a.out or OUT / Path(a.image).stem); out.mkdir(parents=True, exist_ok=True)
    if a.box:
        boxes = [(1.0, [float(v) for v in a.box.split(",")])]
    else:
        log(f"finding '{a.what}'...")
        boxes = find_boxes(img, a.what, a.all or a.merge, a.pick, out / f"{Path(a.image).stem}_found.jpg")
    log(f"masking {len(boxes)} object(s) with SAM 2.1...")
    masks = sam_masks(img, [b for _, b in boxes])
    # clean each object's edge on its own (BiRefNet looks for ONE main subject per crop)
    alphas = []
    for (score, box), m in zip(boxes, masks):
        al, how = (m, "sam") if a.edge == "sam" else birefnet_refine(img, box, m)
        alphas.append((score, box, drop_scraps(al), how))
    if a.merge and len(alphas) > 1:                      # several things as ONE cut-out (e.g. a person + what they hold)
        alphas = [(max(x[0] for x in alphas), None, np.max([x[2] for x in alphas], axis=0),
                   "+".join(sorted({x[3] for x in alphas})))]
    results = []
    union = np.zeros(img.size[::-1], np.float32)
    for k, (score, box, alpha, how) in enumerate(alphas):
        union = np.maximum(union, alpha)
        ys, xs = np.where(alpha > 0.02)
        if len(xs) == 0:
            continue
        x0, y0, x1, y1 = xs.min(), ys.min(), xs.max() + 1, ys.max() + 1
        rgba = np.dstack([np.asarray(img), (alpha * 255).astype(np.uint8)])[y0:y1, x0:x1]
        tag = Path(a.image).stem + ("" if len(alphas) == 1 else f"_{k + 1}")
        cp = out / f"{tag}_cutout.png"
        Image.fromarray(rgba, "RGBA").save(cp)
        results.append({"cutout": str(cp), "x": int(x0), "y": int(y0), "w": int(x1 - x0), "h": int(y1 - y0),
                        "score": round(score, 3), "edge": how})
    mp = out / f"{Path(a.image).stem}_mask.png"
    Image.fromarray((union * 255).astype(np.uint8), "L").save(mp)
    print(json.dumps({"mask": str(mp), "image_size": list(img.size), "objects": results}))


# ------------------------------------------------------------------ remove (LaMa)
def lama_fill(img, mask):
    model = torch.jit.load(str(MODELS / "big-lama.pt"), map_location=DEV).eval()
    W, H = img.size
    s = min(1.0, 2048 / max(W, H))                         # LaMa works best up to ~2k
    w, h = int(W * s) // 8 * 8, int(H * s) // 8 * 8
    im = np.asarray(img.resize((w, h), Image.LANCZOS), np.float32) / 255
    mk = (np.asarray(mask.resize((w, h), Image.BILINEAR), np.float32) / 255 > 0.5).astype(np.float32)
    ti = torch.from_numpy(im.transpose(2, 0, 1)[None]).to(DEV)
    tm = torch.from_numpy(mk[None, None]).to(DEV)
    with torch.no_grad():
        res = model(ti, tm)[0].permute(1, 2, 0).clamp(0, 1).float().cpu().numpy()
    filled = Image.fromarray((res * 255 + 0.5).astype(np.uint8)).resize((W, H), Image.LANCZOS)
    # only replace the masked area (feathered) so the rest keeps full original detail
    soft = mask.filter(ImageFilter.GaussianBlur(2))
    return Image.composite(filled, img, soft)


def cmd_remove(a):
    img = load_rgb(a.image)
    out = Path(a.out or OUT / Path(a.image).stem); out.mkdir(parents=True, exist_ok=True)
    if a.mask:
        mask = Image.open(a.mask).convert("L").resize(img.size)
    else:
        log(f"finding '{a.what}'...")
        boxes = find_boxes(img, a.what, a.all, a.pick, out / f"{Path(a.image).stem}_found.jpg")
        m = np.max(sam_masks(img, [b for _, b in boxes]), axis=0)
        mask = Image.fromarray((m * 255).astype(np.uint8), "L")
    grow = max(5, int(0.012 * max(img.size)))             # cover the object's halo too
    mask = mask.filter(ImageFilter.MaxFilter(2 * (grow // 2) + 1))
    log("filling with LaMa...")
    res = lama_fill(img, mask)
    rp = out / f"{Path(a.image).stem}_removed.png"
    res.save(rp)
    mask.save(out / f"{Path(a.image).stem}_removed_mask.png")
    print(json.dumps({"removed": str(rp), "mask": str(out / f'{Path(a.image).stem}_removed_mask.png')}))


# ------------------------------------------------------------------ match colour + shadow
def cmd_match(a):
    import cv2
    cut = Image.open(a.cutout).convert("RGBA")
    tgt = load_rgb(a.target)
    if a.region:
        tgt = tgt.crop(tuple(int(v) for v in a.region.split(",")))
    c = np.asarray(cut, np.float32)
    rgb, al = c[..., :3].astype(np.uint8), c[..., 3] / 255
    lab_c = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    lab_t = cv2.cvtColor(np.asarray(tgt), cv2.COLOR_RGB2LAB).astype(np.float32).reshape(-1, 3)
    sel = lab_c[al > 0.5]
    mc, sc = sel.mean(0), sel.std(0) + 1e-3
    mt, st = lab_t.mean(0), lab_t.std(0) + 1e-3
    k = a.strength
    new = (lab_c - mc) * (1 + k * (st / sc - 1)) + mc + k * (mt - mc)
    new[..., 0] = np.clip(new[..., 0], 0, 255)
    out_rgb = cv2.cvtColor(np.clip(new, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)
    res = Image.fromarray(np.dstack([out_rgb, c[..., 3].astype(np.uint8)]), "RGBA")
    if a.shadow:
        pad = int(0.08 * max(res.size)); off = (int(0.025 * res.width), int(0.035 * res.height))
        big = Image.new("RGBA", (res.width + 2 * pad, res.height + 2 * pad), (0, 0, 0, 0))
        sh = Image.new("L", big.size, 0); sh.paste(res.split()[3], (pad + off[0], pad + off[1]))
        sh = sh.filter(ImageFilter.GaussianBlur(pad / 3)).point(lambda v: int(v * 0.5))
        big.paste(Image.new("RGBA", big.size, (0, 0, 0, 255)), (0, 0), sh)
        big.alpha_composite(res, (pad, pad))
        res = big
    out = Path(a.out or Path(a.cutout).parent); out.mkdir(parents=True, exist_ok=True)
    mp = out / (Path(a.cutout).stem.replace("_cutout", "") + "_matched.png")
    res.save(mp)
    print(json.dumps({"matched": str(mp), "w": res.width, "h": res.height, "shadow_pad": pad if a.shadow else 0}))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("cut"); c.add_argument("image"); c.add_argument("--what"); c.add_argument("--box")
    c.add_argument("--all", action="store_true"); c.add_argument("--edge", choices=["auto", "sam"], default="auto")
    c.add_argument("--pick", help="which match(es) to use, e.g. 2 or 1,3 (numbers from the _found.jpg preview)")
    c.add_argument("--merge", action="store_true", help="all matches as ONE cut-out (e.g. --what 'dog, ball')")
    c.add_argument("--out")
    r = sub.add_parser("remove"); r.add_argument("image"); r.add_argument("--what"); r.add_argument("--mask")
    r.add_argument("--all", action="store_true"); r.add_argument("--pick"); r.add_argument("--out")
    m = sub.add_parser("match"); m.add_argument("cutout"); m.add_argument("target"); m.add_argument("--region")
    m.add_argument("--strength", type=float, default=0.5); m.add_argument("--shadow", action="store_true")
    m.add_argument("--out")
    a = ap.parse_args()
    if a.cmd in ("cut", "remove") and not (a.what or getattr(a, "box", None) or getattr(a, "mask", None)):
        ap.error("say what to cut/remove with --what (or give --box / --mask)")
    t = time.time()
    log(f"device: {torch.cuda.get_device_name(0) if DEV == 'cuda' else 'CPU'}")
    {"cut": cmd_cut, "remove": cmd_remove, "match": cmd_match}[a.cmd](a)
    log(f"done in {time.time() - t:.1f} s")


if __name__ == "__main__":
    main()
