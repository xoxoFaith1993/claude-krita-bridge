"""Smoke test against a running Krita with the Claude Bridge plugin (no AI tools needed).

New canvas, two generated picture layers, move / rotate / blend, status, snapshot, export.
  python tests\\smoke.py
"""
import os
import struct
import sys
import tempfile
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server"))
import server as S  # noqa: E402

TMP = os.path.join(tempfile.gettempdir(), "krita-bridge-smoke")
os.makedirs(TMP, exist_ok=True)


def png(path, w, h, rgba):
    """A plain one-colour test PNG (no Pillow needed)."""
    raw = b"".join(b"\x00" + bytes(rgba) * w for _ in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    return path


def call(tool, **a):
    return S.TOOL_MAP[tool][4](a)


a = png(os.path.join(TMP, "square_a.png"), 400, 300, (40, 90, 200, 255))
b = png(os.path.join(TMP, "square_b.png"), 240, 240, (220, 180, 40, 200))
print(call("krita_new", w=1280, h=720, name="Bridge smoke test", background="#202020"))
print(call("krita_add_image", path=a, name="Blue box", x=200, y=150))
print(call("krita_add_image", path=b, name="Yellow box", x=600, y=260, opacity=80))
print(call("krita_layer", layer="Yellow box", rotate=-8, move_by=[-40, 20]))
print(call("krita_layer", layer="Blue box", blend="multiply"))
st = call("krita_status")
for l in st["active"]["layers"]:
    print("  layer:", l["name"], l["type"], "opacity", l["opacity"], "label", l["label"], (l["x"], l["y"], l["w"], l["h"]))
snap = call("krita_snapshot", max_side=960)
print("snapshot:", snap["file"], snap["shown"])
print(call("krita_export", path=os.path.join(TMP, "smoke_export.png")))
print("smoke test done")
