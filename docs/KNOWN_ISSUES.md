# Known rough edges

The honest list. It's a work in progress, and fixes are welcome.

- **Tested on one setup:** Krita 5.3 on Windows 11. Other 5.x versions should work. macOS and Linux are
  untested: the plugin is plain PyQt and the server plain Python, but paths like `%APPDATA%` are assumed.
- **Portable Krita** keeps its resources elsewhere: use `install_plugin.py --resources`.
- **The plugin is enabled through `kritarc`.** If Krita is open while you install, it may overwrite that file
  when it quits: close Krita first, or tick the plugin in the Python Plugin Manager.
- **Fixed port 47821.** If something else uses it, change `PORT` in the plugin and `"port"` in `config.json` to
  the same number.
- **Long jobs block Krita's interface** while they run, because the code runs on Krita's GUI thread (big filters,
  huge images).
- **`krita_layer` raise/lower** use Krita's own Move Layer Up/Down actions on the active layer, so they also make
  that layer active.
- **Snapshots are scaled down** (`max_side`, default 1280) to keep replies small.
- **AI tools:** the models load fresh each call (about a minute per run) to keep GPU memory free. A name search
  can pick the wrong object, so use the numbered preview and `pick`. LaMa smears very large holes. See
  [ai_tools/README.md](../ai_tools/README.md).
- **Local AI check:** small vision models judge cut-outs well but not perfectly. If a correct piece is refused,
  run again with `add_anyway=true`; to skip the check, use `check=false`.
- **Microsoft Store / Python Install Manager Pythons** see a private copy of `%APPDATA%`. A plugin installed
  with one can be invisible to Krita, so `install_plugin.py` refuses to run with one. Use the installer (it
  bundles its own Python) or Python from python.org.
- **Both bridges share one Ollama safely:** the watcher waits until FL Studio *and* Krita are closed before it
  stops an Ollama it started, and it never stops one it didn't start (it checks the exact process).
- `krita_exec` runs any Python inside Krita, by design (localhost only, token-protected).
