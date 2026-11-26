"""Install / update the Claude Bridge plugin into Krita's user folder and switch it on.

  python install_plugin.py                      # normal Krita: %APPDATA%\\krita\\pykrita
  python install_plugin.py --resources DIR      # Krita with a custom resource folder (e.g. a portable copy)
  python install_plugin.py --uninstall

Close Krita first, or the "enabled" flag may be overwritten when Krita quits.
"""
import argparse
import os
import shutil

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--resources", help="Krita resource folder (default %%APPDATA%%\\krita)")
ap.add_argument("--kritarc", help="kritarc file (default %%LOCALAPPDATA%%\\kritarc)")
ap.add_argument("--uninstall", action="store_true")
a = ap.parse_args()

try:   # Store / Install Manager Pythons write AppData into a private copy that Krita never sees
    import ctypes
    _n = ctypes.c_uint32(0)
    if not (a.resources and a.kritarc) and ctypes.windll.kernel32.GetCurrentPackageFullName(ctypes.byref(_n), None) != 15700:
        raise SystemExit('This Python is a Microsoft Store / Python Install Manager build: it writes AppData into a '
                         'private copy that Krita cannot see. Run this with the installer\'s bundled Python or '
                         'Python from python.org (or pass both --resources and --kritarc with the real paths).')
except (AttributeError, OSError):
    pass

src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "krita_plugin")
pykrita = os.path.join(a.resources or os.path.join(os.environ["APPDATA"], "krita"), "pykrita")
dst = os.path.join(pykrita, "claude_bridge")
if a.uninstall:
    shutil.rmtree(dst, ignore_errors=True)
    try:
        os.remove(os.path.join(pykrita, "claude_bridge.desktop"))
    except OSError:
        pass
    print("plugin removed from", pykrita)
else:
    os.makedirs(pykrita, exist_ok=True)
    shutil.copy(os.path.join(src, "claude_bridge.desktop"), pykrita)
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(os.path.join(src, "claude_bridge"), dst, ignore=shutil.ignore_patterns("__pycache__"))
    print("plugin copied to", dst)

# Krita keeps "plugin enabled" flags in kritarc, section [python]
rc = a.kritarc or os.path.join(os.environ["LOCALAPPDATA"], "kritarc")
lines = open(rc, encoding="utf-8").read().splitlines() if os.path.exists(rc) else []
if "[python]" not in lines:
    lines += ["", "[python]"]
i = lines.index("[python]")
j = i + 1
while j < len(lines) and not lines[j].startswith("["):
    j += 1
block = [l for l in lines[i + 1:j] if not l.startswith("enable_claude_bridge=")]
lines[i + 1:j] = block + ([] if a.uninstall else ["enable_claude_bridge=true"])
with open(rc, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print(("disabled in " if a.uninstall else "enabled in ") + rc)
