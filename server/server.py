"""Krita MCP server: gives Claude tools to control a running Krita through the Claude Bridge plugin.

Speaks MCP (JSON-RPC 2.0, one JSON object per line) over stdin/stdout. No packages needed (same design as the
FL Studio bridge). The plugin listens on 127.0.0.1:47821 with a token in %APPDATA%\\krita\\claude_bridge_token.txt.
Every layer Claude adds gets a colour label (red by default, "layer_label" in config.json), so the user can tell
Claude's work from their own.
"""
import base64, json, os, socket, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402

PROTOCOL_VERSION = "2025-06-18"
VERSION = "0.1.0"
CFG = config.CFG
PORT = int(CFG["port"])
TOKEN_FILE = os.path.join(os.environ.get("APPDATA", ""), "krita", "claude_bridge_token.txt")
SNAP_DIR = CFG["snap_dir"]
LABEL = int(CFG["layer_label"])  # Krita colour labels: 0 none, 1 blue, 2 green, 3 yellow, 4 orange, 5 brown, 6 red, 7 purple, 8 grey


class BridgeError(Exception):
    pass


def kr(code, timeout=120, **args):
    """Run a code body inside Krita with ARGS available. Returns the value of the expression / `result`."""
    try:
        token = open(TOKEN_FILE).read().strip()
    except OSError:
        raise BridgeError("Krita isn't running with the Claude Bridge plugin (no token file). Use krita_launch, or krita_doctor for a step-by-step check.")
    try:
        s = socket.create_connection(("127.0.0.1", PORT), timeout=5)
    except OSError:
        raise BridgeError("Can't reach Krita on port %d. Is Krita open? Use krita_launch, or krita_doctor for a step-by-step check." % PORT)
    s.settimeout(timeout)
    args["_new_label"] = LABEL             # colour label for NEW layers only (ADD_IMAGE); never applied to edits
    s.sendall(json.dumps({"token": token, "code": code, "args": args}).encode("utf-8") + b"\n")
    buf = b""
    while b"\n" not in buf:
        chunk = s.recv(1 << 20)
        if not chunk:
            break
        buf += chunk
    s.close()
    reply = json.loads(buf.decode("utf-8"))
    if not reply.get("ok"):
        raise BridgeError(reply.get("error", "?") + ("\n" + reply.get("trace", "") if reply.get("trace") else ""))
    if reply.get("stdout"):
        return {"result": reply["result"], "printed": reply["stdout"]}
    return reply["result"]


# ---------------------------------------------------------------- code bodies run inside Krita
LAYER_INFO = r'''
def info(n, depth=0):
    b = n.bounds()
    return {"name": n.name(), "uid": n.uniqueId().toString(), "type": n.type(), "visible": n.visible(),
            "opacity": round(n.opacity() / 255 * 100), "blend": n.blendingMode(), "label": n.colorLabel(),
            "locked": n.locked(), "x": b.x(), "y": b.y(), "w": b.width(), "h": b.height(), "depth": depth,
            "children": [info(c, depth + 1) for c in n.childNodes()] if n.type() == "grouplayer" else None}
'''

STATUS = LAYER_INFO + r'''
docs = [{"name": d.name(), "file": d.fileName(), "w": d.width(), "h": d.height()} for d in app.documents()]
result = {"krita": app.version(), "documents": docs, "active": None}
if doc is not None:
    result["active"] = {"name": doc.name(), "file": doc.fileName(), "w": doc.width(), "h": doc.height(),
                        "model": doc.colorModel() + "/" + doc.colorDepth(), "dpi": doc.resolution(),
                        "active_layer": doc.activeNode().name() if doc.activeNode() else None,
                        "layers": [info(n) for n in reversed(doc.topLevelNodes())]}   # top of the stack first
'''

NEW_DOC = r'''
d = app.createDocument(args["w"], args["h"], args.get("name", "Untitled"), "RGBA", "U8", "", 300.0)
app.activeWindow().addView(d)
bg = d.topLevelNodes()[0] if d.topLevelNodes() else None
if bg is not None and args.get("background"):
    from PyQt5.QtGui import QColor
    c = QColor(args["background"]); img = QImage(d.width(), d.height(), QImage.Format_ARGB32); img.fill(c)
    ptr = img.constBits(); ptr.setsize(img.byteCount()); bg.setPixelData(bytes(ptr), 0, 0, d.width(), d.height())
d.refreshProjection()
result = {"name": d.name(), "w": d.width(), "h": d.height()}
'''

OPEN_DOC = r'''
d = app.openDocument(args["path"])
if d is None:
    raise RuntimeError("could not open " + args["path"])
app.activeWindow().addView(d)
result = {"name": d.name(), "w": d.width(), "h": d.height()}
'''

ADD_IMAGE = r'''
import os
if doc is None:
    raise RuntimeError("no document open")
img = QImage(args["path"])
if img.isNull():
    raise RuntimeError("can't read image " + args["path"])
s = args.get("scale") or 1
fit = args.get("fit")                                     # contain / cover / width / height: relative to the canvas
if fit:
    fx, fy = doc.width() / img.width(), doc.height() / img.height()
    s *= {"contain": min(fx, fy), "cover": max(fx, fy), "width": fx, "height": fy}[fit]
if s and s != 1:
    from PyQt5.QtCore import Qt
    img = img.scaled(max(1, round(img.width() * s)), max(1, round(img.height() * s)), Qt.KeepAspectRatio, Qt.SmoothTransformation)
img = img.convertToFormat(QImage.Format_ARGB32)          # BGRA bytes in memory = Krita's RGBA/U8 layout
name = args.get("name") or os.path.splitext(os.path.basename(args["path"]))[0]
n = doc.createNode(name, "paintlayer")
x, y = args.get("x"), args.get("y")
if x is None: x = (doc.width() - img.width()) // 2
if y is None: y = (doc.height() - img.height()) // 2
ptr = img.constBits(); ptr.setsize(img.byteCount())
n.setPixelData(bytes(ptr), int(x), int(y), img.width(), img.height())
n.setColorLabel(args.get("label", args.get("_new_label", 6)))   # "layer_label" from config.json
if args.get("opacity") is not None: n.setOpacity(round(args["opacity"] / 100 * 255))
if args.get("blend"): n.setBlendingMode(args["blend"])
parent = node_by(args["parent"]) if args.get("parent") else doc.rootNode()
above = node_by(args["above"]) if args.get("above") else None
parent.addChildNode(n, above)
doc.setActiveNode(n)
refresh()
b = n.bounds()
result = {"layer": n.name(), "uid": n.uniqueId().toString(), "x": b.x(), "y": b.y(), "w": b.width(), "h": b.height()}
'''

LAYER_SET = r'''
n = node_by(args.get("layer"))
a = args
if a.get("rename"): n.setName(a["rename"])
if a.get("visible") is not None: n.setVisible(a["visible"])
if a.get("opacity") is not None: n.setOpacity(round(a["opacity"] / 100 * 255))
if a.get("blend"): n.setBlendingMode(a["blend"])
if a.get("label") is not None: n.setColorLabel(a["label"])
if a.get("locked") is not None: n.setLocked(a["locked"])
if a.get("move_to") is not None:                       # absolute top-left of the layer's content
    b = n.bounds(); n.move(n.position().x() + a["move_to"][0] - b.x(), n.position().y() + a["move_to"][1] - b.y())
if a.get("move_by") is not None:
    n.move(n.position().x() + a["move_by"][0], n.position().y() + a["move_by"][1])
if a.get("scale") is not None and a["scale"] != 1:
    b = n.bounds()
    n.scaleNode(QPointF(b.x() + b.width() / 2, b.y() + b.height() / 2),
                max(1, round(b.width() * a["scale"])), max(1, round(b.height() * a["scale"])), "Bicubic")
if a.get("rotate") is not None:
    import math
    n.rotateNode(math.radians(a["rotate"]))
if a.get("flip") == "horizontal": n.mirrorHorizontal()
elif a.get("flip") == "vertical": n.mirrorVertical()
if a.get("duplicate"):
    c = n.duplicate(); c.setName(n.name() + " copy"); n.parentNode().addChildNode(c, n); n = c
if a.get("raise") or a.get("lower"):                    # Krita's own Move Layer Up/Down actions
    doc.setActiveNode(n)
    app.action("move_layer_up" if a.get("raise") else "move_layer_down").trigger()
if a.get("delete"):
    name = n.name(); n.remove(); refresh(); result = {"deleted": name}
else:
    doc.setActiveNode(n); refresh(); b = n.bounds()
    result = {"layer": n.name(), "x": b.x(), "y": b.y(), "w": b.width(), "h": b.height(),
              "opacity": round(n.opacity() / 255 * 100), "visible": n.visible(), "blend": n.blendingMode()}
'''

MASK_FROM_FILE = r'''
n = node_by(args.get("layer"))
img = QImage(args["path"]).convertToFormat(QImage.Format_Grayscale8)
if img.isNull():
    raise RuntimeError("can't read mask " + args["path"])
if img.width() != doc.width() or img.height() != doc.height():
    from PyQt5.QtCore import Qt
    img = img.scaled(doc.width(), doc.height(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
if args.get("invert"): img.invertPixels()
rows = []
ptr = img.constBits(); ptr.setsize(img.bytesPerLine() * img.height()); raw = bytes(ptr)
for yy in range(img.height()):
    rows.append(raw[yy * img.bytesPerLine(): yy * img.bytesPerLine() + img.width()])
m = doc.createTransparencyMask(args.get("name", "mask"))
sel = Selection(); sel.setPixelData(b"".join(rows), 0, 0, img.width(), img.height())
m.setSelection(sel)
n.addChildNode(m, None)
refresh()
result = {"mask": m.name(), "on": n.name()}
'''

SELECT = r'''
if args.get("mode") == "none":
    doc.setSelection(None); result = "selection cleared"
elif args.get("mode") == "all":
    s = Selection(); s.select(0, 0, doc.width(), doc.height(), 255); doc.setSelection(s); result = "all selected"
elif args.get("mode") == "rect":
    x, y, w, h = args["rect"]; s = Selection(); s.select(x, y, w, h, 255); doc.setSelection(s); result = "rect selected"
elif args.get("mode") == "from_file":
    img = QImage(args["path"]).convertToFormat(QImage.Format_Grayscale8)
    ptr = img.constBits(); ptr.setsize(img.bytesPerLine() * img.height()); raw = bytes(ptr)
    data = b"".join(raw[yy * img.bytesPerLine(): yy * img.bytesPerLine() + img.width()] for yy in range(img.height()))
    s = Selection(); s.setPixelData(data, 0, 0, img.width(), img.height()); doc.setSelection(s); result = "selection loaded"
'''

FILTER = r'''
n = node_by(args.get("layer"))
f = app.filter(args["name"])
if f is None:
    raise RuntimeError("no filter %r; known: %s" % (args["name"], ", ".join(sorted(app.filters()))))
cfg = f.configuration()
for k, v in (args.get("params") or {}).items():
    cfg.setProperty(k, v)
f.setConfiguration(cfg)
b = n.bounds()
f.apply(n, b.x(), b.y(), b.width(), b.height())
refresh()
result = {"applied": args["name"], "on": n.name()}
'''

EXPORT = r'''
if doc is None:
    raise RuntimeError("no document open")
doc.setBatchmode(True)
try:
    ok = doc.exportImage(args["path"], InfoObject())
finally:
    doc.setBatchmode(False)
result = {"exported": args["path"], "ok": bool(ok)}
'''

SAVE = r'''
if doc is None:
    raise RuntimeError("no document open")
if args.get("path"):
    ok = doc.saveAs(args["path"])
else:
    ok = doc.save()
result = {"saved": doc.fileName(), "ok": bool(ok)}
'''

SNAPSHOT = r'''
if doc is None:
    raise RuntimeError("no document open")
from PyQt5.QtCore import Qt
refresh()
if args.get("layer"):
    n = node_by(args["layer"]); b = n.bounds()
    img = n.thumbnail(b.width(), b.height()) if b.width() and b.height() else QImage()
else:
    img = doc.projection(0, 0, doc.width(), doc.height())
m = args.get("max_side", 1280)
if max(img.width(), img.height()) > m:
    img = img.scaled(m, m, Qt.KeepAspectRatio, Qt.SmoothTransformation)
img.save(args["out"], "PNG")
result = {"w": doc.width(), "h": doc.height(), "shown": [img.width(), img.height()]}
'''


SHOW = r'''
from PyQt5.QtCore import Qt
w = app.activeWindow().qwindow()
w.setWindowState((w.windowState() & ~Qt.WindowMinimized) | Qt.WindowMaximized | Qt.WindowActive)
w.show(); w.raise_(); w.activateWindow()
result = {"title": w.windowTitle(), "docs": [d.name() for d in app.documents()]}
'''


# ---------------------------------------------------------------- tools
def launch(a):
    try:
        return {"already_running": True, "status": kr(STATUS)}
    except BridgeError:
        pass
    exe = CFG.get("krita_exe")
    if not exe or not os.path.isfile(exe):
        raise BridgeError("krita.exe not found. Start Krita yourself, or set \"krita_exe\" in %s" % config.CONFIG_FILE)
    args = [exe, "--nosplash"] + ([a["path"]] if a.get("path") else [])
    subprocess.Popen(args, creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    t0 = time.time()
    while time.time() - t0 < 90:
        time.sleep(2)
        try:
            return {"launched": True, "seconds": round(time.time() - t0), "status": kr(STATUS)}
        except BridgeError:
            continue
    raise BridgeError("Krita started but the Claude Bridge plugin didn't answer within 90 s. "
                      "Check Settings > Configure Krita > Python Plugin Manager: 'Claude Bridge' must be ticked "
                      "(then restart Krita).")


def look(a):
    """Optional local vision: describe the canvas (or a layer) with the local model."""
    import local_eyes
    ok, why = local_eyes.available()
    if not ok:
        raise BridgeError("krita_look needs the optional local AI: " + why)
    snap = snapshot({"layer": a.get("layer"), "max_side": a.get("max_side", 1024)})
    desc = local_eyes.look(snap["file"])
    return {"description": desc, "model": local_eyes.MODEL, "file": snap["file"], "_image": snap["_image"]}


def snapshot(a):
    os.makedirs(SNAP_DIR, exist_ok=True)
    out = os.path.join(SNAP_DIR, "snap_%d.png" % int(time.time() * 1000))
    info = kr(SNAPSHOT, out=out, layer=a.get("layer"), max_side=a.get("max_side", 1280))
    with open(out, "rb") as f:
        data = base64.b64encode(f.read()).decode("ascii")
    info["file"] = out
    info["_image"] = data
    return info


# ---------------------------------------------------------------- optional AI cut-out tools (ai_tools/, see its README)
AI = CFG["ai"]
CUTOUT_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ai_tools", "cutout.py")
WORK = AI["work_dir"]

EXPORT_LAYER = r'''
n = node_by(args.get("layer"))
b = n.bounds()
if b.width() == 0 or b.height() == 0:
    raise RuntimeError("layer %r is empty" % n.name())
data = n.pixelData(b.x(), b.y(), b.width(), b.height())
img = QImage(data, b.width(), b.height(), QImage.Format_ARGB32)
img.save(args["out"], "PNG")
result = {"layer": n.name(), "uid": n.uniqueId().toString(), "x": b.x(), "y": b.y(), "w": b.width(), "h": b.height()}
'''

EXPORT_REGION = r'''
x, y, w, h = args["rect"]
x, y = max(0, x), max(0, y); w, h = min(w, doc.width() - x), min(h, doc.height() - y)
doc.projection(x, y, w, h).save(args["out"], "PNG")
result = [x, y, w, h]
'''


def _need_ai():
    py = AI.get("python")
    if not py or not os.path.isfile(py):
        raise BridgeError("The AI tools are optional and not set up yet: install them (ai_tools/README.md), then set "
                          "\"ai\": {\"python\": ...} in %s" % config.CONFIG_FILE)
    return py


def _cutout(*argv):
    py = _need_ai()
    tmp = os.path.join(WORK, "tmp")
    os.makedirs(tmp, exist_ok=True)
    env = dict(os.environ, CUTOUT_MODELS=AI["models_dir"], CUTOUT_OUT=os.path.join(WORK, "out"),
               HF_HOME=os.path.join(AI["models_dir"], "hf"), HF_HUB_OFFLINE="1", TEMP=tmp, TMP=tmp,
               **{k: str(v) for k, v in (AI.get("env") or {}).items()})
    r = subprocess.run([py, CUTOUT_PY, *argv], capture_output=True, text=True, timeout=int(AI["timeout_seconds"]),
                       env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    lines = [l for l in r.stdout.splitlines() if l.strip().startswith("{")]
    if r.returncode != 0 or not lines:
        raise BridgeError("cutout failed:\n" + (r.stderr or r.stdout)[-1500:])
    found = [l.strip() for l in r.stderr.splitlines() if l.strip().startswith("#")]
    return json.loads(lines[-1]), found


def _source(a, tag):
    """The picture to work on: a file path, or a Krita layer exported at full size (with its canvas offset)."""
    os.makedirs(WORK, exist_ok=True)
    if a.get("path"):
        return a["path"], 0, 0, None
    out = os.path.join(WORK, "%s_%d.png" % (tag, int(time.time() * 1000)))
    info = kr(EXPORT_LAYER, layer=a.get("layer"), out=out)
    return out, info["x"], info["y"], info["name"] if "name" in info else info["layer"]


def _found_image(src, res_dir):
    p = os.path.join(res_dir, os.path.splitext(os.path.basename(src))[0] + "_found.jpg")
    if os.path.exists(p):
        with open(p, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii")
    return None


def cutout(a):
    _need_ai()
    src, ox, oy, layer = _source(a, "cut")
    res_dir = os.path.join(WORK, "out", os.path.splitext(os.path.basename(src))[0])
    argv = ["cut", src, "--out", res_dir]
    for k in ("what", "pick", "box"):
        if a.get(k):
            argv += ["--" + k, str(a[k])]
    if a.get("merge"): argv.append("--merge")
    if a.get("all"): argv.append("--all")
    res, found = _cutout(*argv)
    out = {"matches": found, "objects": res["objects"], "mask": res["mask"]}
    # optional: the local vision model checks each piece really is what was asked for (catches a wrong match)
    wrong = []
    if a.get("what") and not a.get("box") and CFG["local_ai"].get("check_cutouts", True) and a.get("check", True):
        try:
            import local_eyes
            ok, why = local_eyes.available()
        except Exception as e:
            ok, why = False, 'local check unavailable (%s)' % e
        if ok:
            checks = []
            for i, o in enumerate(res["objects"], 1):
                try:
                    c = local_eyes.check_piece(o.get("check_preview") or o["cutout"], a["what"])
                except Exception as e:
                    c = {"error": str(e)}
                checks.append(dict(c, piece=i))
                if c.get("match") is False:
                    wrong.append(i)
            out["local_check"] = checks
        else:
            out["local_check"] = "skipped: " + why
    if wrong and not a.get("add_anyway"):
        out["added_layers"] = []
        out["warning"] = ("The local vision model says piece(s) %s don't look like '%s', so nothing was added. Look at "
                          "the numbered preview, then run again with pick='N' (or add_anyway=true if it's right)."
                          % (", ".join(map(str, wrong)), a["what"]))
    elif a.get("add", True):
        added = []
        for o in res["objects"]:
            name = a.get("name") or ((a.get("what") or "cutout").split(",")[0].strip() + " (cut out)")
            added.append(kr(ADD_IMAGE, path=o["cutout"], name=name, x=ox + o["x"], y=oy + o["y"],
                            above=layer if layer else None))
        out["added_layers"] = added
    img = _found_image(src, res_dir)
    if img:
        out["_image"] = img
    return out


def remove(a):
    _need_ai()
    src, ox, oy, layer = _source(a, "rm")
    res_dir = os.path.join(WORK, "out", os.path.splitext(os.path.basename(src))[0])
    argv = ["remove", src, "--out", res_dir]
    for k in ("what", "pick", "mask"):
        if a.get(k):
            argv += ["--" + k, str(a[k])]
    res, found = _cutout(*argv)
    name = (layer or "picture") + " (removed: %s)" % (a.get("what") or "mask")
    added = kr(ADD_IMAGE, path=res["removed"], name=name, x=ox, y=oy, above=layer if layer else None)
    if layer and a.get("hide_original", True):
        kr(LAYER_SET, layer=layer, visible=False)
    out = {"matches": found, "added_layer": added, "original_hidden": bool(layer and a.get("hide_original", True))}
    img = _found_image(src, res_dir)
    if img:
        out["_image"] = img
    return out


def match(a):
    """Recolour a cut-out layer toward what's under it on the canvas (or a given region), optional shadow."""
    _need_ai()
    os.makedirs(WORK, exist_ok=True)
    t = int(time.time() * 1000)
    cut = os.path.join(WORK, "match_cut_%d.png" % t)
    info = kr(EXPORT_LAYER, layer=a["layer"], out=cut)
    rect = a.get("region") or [info["x"] - info["w"] // 2, info["y"] - info["h"] // 2, info["w"] * 2, info["h"] * 2]
    tgt = os.path.join(WORK, "match_tgt_%d.png" % t)
    kr(EXPORT_REGION, rect=rect, out=tgt)
    argv = ["match", cut, tgt, "--strength", str(a.get("strength", 0.5)), "--out", WORK]
    if a.get("shadow"): argv.append("--shadow")
    res, _ = _cutout(*argv)
    pad = res.get("shadow_pad", 0)
    added = kr(ADD_IMAGE, path=res["matched"], name=info["layer"] + " (matched)", x=info["x"] - pad, y=info["y"] - pad,
               above=info["layer"])
    kr(LAYER_SET, layer=info["uid"], visible=False)
    return {"added_layer": added, "original_hidden": True, "matched_to": rect}


NUM = {"type": "number"}
INT = {"type": "integer"}
BOOL = {"type": "boolean"}
STR = {"type": "string"}
PAIR = {"type": "array", "items": NUM, "minItems": 2, "maxItems": 2}

TOOLS = [
    ("krita_doctor", "Check every link from Claude to Krita and say what is wrong and how to fix it: settings, Krita program, plugin installed / up to date / switched on, Krita running, port, token, document open, optional AI tools (Python, models; deep=true also tests PyTorch, which briefly uses a lot of memory) and optional local AI (Ollama, vision model). Read-only: starts nothing. Use it first when a tool fails, and give the user the fix lines in plain words.",
     {"deep": BOOL}, [], lambda a: __import__("doctor").diagnose(kr, bool(a.get("deep")))),
    ("krita_launch", "Start Krita (if it isn't open) and wait for the Claude Bridge plugin. Optionally open a file. Returns krita_status.",
     {"path": STR}, [], launch),
    ("krita_status", "Krita version, open documents, and the active document's size and layer stack (top first: name, uid, type, visible, opacity 0-100, blend, colour label, bounds). Use first.",
     {}, [], lambda a: kr(STATUS)),
    ("krita_new", "Create a new RGBA document (pixels) and show it. background as '#RRGGBB' (optional).",
     {"w": INT, "h": INT, "name": STR, "background": STR}, ["w", "h"], lambda a: kr(NEW_DOC, **a)),
    ("krita_open", "Open an image or .kra file in Krita and show it.", {"path": STR}, ["path"], lambda a: kr(OPEN_DOC, **a)),
    ("krita_add_image", "Add a picture file (PNG cutout, JPG...) as a new paint layer in the active document. Centred unless x/y (top-left, px) are given. fit (contain/cover/width/height) sizes it to the canvas first; scale then multiplies. Gets a red colour label (Claude's work). above = put it above that layer; parent = inside that group.",
     {"path": STR, "name": STR, "x": INT, "y": INT, "fit": {"type": "string", "enum": ["contain", "cover", "width", "height"]},
      "scale": NUM, "opacity": NUM, "blend": STR, "above": STR, "parent": STR},
     ["path"], lambda a: kr(ADD_IMAGE, **a)),
    ("krita_layer", "Change a layer (by name or uid; default the active layer): rename, visible, opacity 0-100, blend mode (e.g. normal, multiply, screen, overlay, soft_light_svg, color), colour label 0-8, locked, move_to [x,y] (content top-left), move_by [dx,dy], scale (factor, about its centre), rotate (degrees), flip horizontal/vertical, duplicate, raise / lower one step, delete.",
     {"layer": STR, "rename": STR, "visible": BOOL, "opacity": NUM, "blend": STR, "label": INT, "locked": BOOL,
      "move_to": PAIR, "move_by": PAIR, "scale": NUM, "rotate": NUM, "flip": {"type": "string", "enum": ["horizontal", "vertical"]},
      "duplicate": BOOL, "raise": BOOL, "lower": BOOL, "delete": BOOL}, [], lambda a: kr(LAYER_SET, **a)),
    ("krita_mask", "Add a transparency mask to a layer from a greyscale image (white = keep, black = hide), e.g. a cutout mask from SAM/BiRefNet. Scaled to the canvas if sizes differ.",
     {"layer": STR, "path": STR, "invert": BOOL, "name": STR}, ["path"], lambda a: kr(MASK_FROM_FILE, **a)),
    ("krita_select", "Set the selection: none, all, rect [x,y,w,h], or from_file (greyscale image, white = selected).",
     {"mode": {"type": "string", "enum": ["none", "all", "rect", "from_file"]}, "rect": {"type": "array", "items": INT}, "path": STR},
     ["mode"], lambda a: kr(SELECT, **a)),
    ("krita_filter", "Apply a Krita filter to a layer, e.g. 'gaussian blur' {horizRadius, vertRadius}, 'unsharp', 'desaturate', 'levels', 'hsvadjustment' {h,s,v}. Unknown names list the available filters.",
     {"layer": STR, "name": STR, "params": {"type": "object"}}, ["name"], lambda a: kr(FILTER, **a)),
    ("krita_snapshot", "See the canvas (or one layer): returns a PNG of what the user sees, scaled to max_side (default 1280). Use after changes and to see the user's own hand edits.",
     {"layer": STR, "max_side": INT}, [], snapshot),
    ("krita_export", "Export the active document flattened to a file (png/jpg/webp/psd by extension).", {"path": STR}, ["path"], lambda a: kr(EXPORT, **a)),
    ("krita_save", "Save the active document (.kra keeps layers). With path: save as.", {"path": STR}, [], lambda a: kr(SAVE, **a)),
    ("krita_cutout", "Optional AI tool (needs ai_tools set up): find an object by name in a layer (default active) or a picture file, mask it exactly (SAM 2.1 + BiRefNet edges) and add it as a new red layer in the same spot. what: 'dog' or several 'dog, ball' (merge=true joins them into one piece). Returns the numbered matches + a preview image of them; if it took the wrong one, run again with pick='2' (or '1,3'). box='x0,y0,x1,y1' skips the search. If the optional local AI (Ollama) is available, each piece is first checked by the local vision model; if any piece doesn't look like `what`, NOTHING is added (see warning; check=false skips the check, add_anyway=true adds regardless). ~1-1.5 min.",
     {"layer": STR, "path": STR, "what": STR, "pick": STR, "merge": BOOL, "all": BOOL, "box": STR, "name": STR, "add": BOOL,
      "check": BOOL, "add_anyway": BOOL},
     [], cutout),
    ("krita_look", "Optional local AI (needs Ollama + a vision model): describe the canvas or one layer offline - summary, subjects, colours, and visible editing problems (hard edges, halos, mismatched light, seams). Returns the description and the picture it looked at. Cheaper than sending big images around; use krita_snapshot to see it yourself.",
     {"layer": STR, "max_side": INT}, [], look),
    ("krita_remove", "Optional AI tool: object removal (content-aware fill, LaMa): erase a named object from a layer (or file) and fill it from its surroundings; adds the result as a new red layer above and hides the original. Best for small/medium things (people in the background, signs, wires); very large areas come out smeary. pick/mask work like krita_cutout.",
     {"layer": STR, "path": STR, "what": STR, "pick": STR, "mask": STR, "hide_original": BOOL}, [], remove),
    ("krita_match", "Optional AI-tools helper: blend a pasted cut-out into the scene: shift its colour/brightness toward what's under it on the canvas (or region [x,y,w,h]), strength 0-1 (default 0.5), optional soft drop shadow. Adds a '(matched)' layer and hides the original.",
     {"layer": STR, "region": {"type": "array", "items": INT}, "strength": NUM, "shadow": BOOL}, ["layer"], match),
    ("krita_show", "Bring Krita's window to the front, maximized (when the user can't see it). Windows may only flash the taskbar icon instead.",
     {}, [], lambda a: kr(SHOW)),
    ("krita_exec", "Run Python inside Krita (names: Krita, app, doc, args, QImage, QPointF, QRect, InfoObject, Selection, node_by(name_or_uid), refresh()). A single expression returns its value; for statements assign to `result`. print() output is returned.",
     {"code": STR}, ["code"], lambda a: kr(a["code"])),
]
TOOL_MAP = {t[0]: t for t in TOOLS}


def tool_list():
    return [{"name": n, "description": d, "inputSchema": {"type": "object", "properties": p, "required": r}}
            for n, d, p, r, _ in TOOLS]


# ---------------------------------------------------------------- MCP plumbing
def send(obj):
    sys.stdout.buffer.write(json.dumps(obj).encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()


def handle(msg):
    method, mid = msg.get("method"), msg.get("id")
    if mid is None:
        return
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": (msg.get("params") or {}).get("protocolVersion") or PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "krita", "version": VERSION},
            "instructions": "Controls a running Krita through the Claude Bridge plugin (localhost). Call krita_launch "
                            "or krita_status first. Layers Claude adds get a colour label (red by default). Use "
                            "krita_snapshot to see the canvas, including the user's own edits. Respect the user's "
                            "hand edits: read a layer's bounds and stacking before replacing it."}})
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": mid, "result": {"tools": tool_list()}})
    elif method == "tools/call":
        params = msg.get("params") or {}
        tool = TOOL_MAP.get(params.get("name"))
        if not tool:
            send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": "Unknown tool"}})
            return
        try:
            value = tool[4](params.get("arguments") or {})
            image = value.pop("_image", None) if isinstance(value, dict) else None
            text, is_error = json.dumps(value, indent=1, ensure_ascii=False), False
        except BridgeError as e:
            text, is_error, image = str(e), True, None
        except Exception as e:
            text, is_error, image = "%s: %s" % (type(e).__name__, e), True, None
        content = [{"type": "text", "text": text}]
        if image:
            content.append({"type": "image", "data": image, "mimeType": "image/png"})
        send({"jsonrpc": "2.0", "id": mid, "result": {"content": content, "isError": is_error}})
    elif method == "ping":
        send({"jsonrpc": "2.0", "id": mid, "result": {}})
    else:
        send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "Method not found: %s" % method}})


def main():
    for line in sys.stdin.buffer:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        handle(msg)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--call":       # quick test: server.py --call tool '{"json":"args"}'
        name = sys.argv[2]; a = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
        v = TOOL_MAP[name][4](a)
        if isinstance(v, dict):
            v.pop("_image", None)
        print(json.dumps(v, indent=1, ensure_ascii=False))
    else:
        main()
