# Architecture

```
┌──────────────┐  MCP over stdio  ┌──────────────────┐  one JSON line per call   ┌──────────────────────────┐
│ Claude Code  │ ───────────────> │ server/server.py │ ────────────────────────> │ Krita                    │
│ (MCP client) │ <─────────────── │                  │ <──────────────────────── │  plugin "Claude Bridge"  │
└──────────────┘  results + PNGs  └──────────────────┘  127.0.0.1:47821 + token   │  (QTcpServer, GUI thread)│
                                     │ optional: subprocess                       └──────────────────────────┘
                                     └──> ai_tools/cutout.py (PyTorch env: DINO, SAM 2.1, BiRefNet, LaMa)
```

| File | Job |
|---|---|
| `krita_plugin/claude_bridge/__init__.py` | Krita `Extension`: a `QTcpServer` on localhost. Each request `{"token", "code", "args"}` runs on Krita's GUI thread with `Krita`, `app`, `doc`, `args`, `QImage`, `QPointF`, `QRect`, `InfoObject`, `Selection`, `node_by()`, `refresh()`; it replies `{"ok", "result", "stdout"}` or `{"ok": false, "error", "trace"}`. |
| `server/server.py` | MCP server (JSON-RPC 2.0 over stdio, standard library only). Holds the code bodies sent to Krita and the `TOOLS` table. |
| `server/config.py` | Settings: defaults, `krita.exe` auto-detection, `config.json`. |
| `ai_tools/cutout.py` | Command-line AI tool run as a subprocess in your PyTorch environment; prints one JSON line. |
| `server/doctor.py` | `krita_doctor`: ordered read-only checks with a plain fix per problem (also `tools/doctor.py`). |
| `server/local_eyes.py`, `ollama_ctl.py`, `ollama_guard.py` | Optional local AI: vision model calls (`krita_look`, the cut-out check), start Ollama on demand, stop it after Krita closes (only if the bridge started it). |
| `install_plugin.py` | Copies the plugin and enables it in `kritarc`. |
| `tools/connect_claude.py` | Registers the MCP server with Claude Code. |

## Security model
- The plugin listens on **127.0.0.1 only**.
- A fresh random token (`secrets.token_hex(16)`) is written to `%APPDATA%\krita\claude_bridge_token.txt` at each
  Krita start, and every request must carry it. Only programs that can read your user profile can drive Krita.
- The code runs with Krita's full Python API, by design.

## Adding a tool
1. Write the Krita-side body as a string in `server.py`: `args` holds the arguments, and you assign the answer
   (JSON-able) to `result`:
   ```python
   INVERT = r'''
   n = node_by(args.get("layer"))
   f = app.filter("invert"); b = n.bounds(); f.apply(n, b.x(), b.y(), b.width(), b.height()); refresh()
   result = {"inverted": n.name()}
   '''
   ```
2. Add a row to `TOOLS`: `(name, description, properties, required, handler)`:
   ```python
   ("krita_invert", "Invert a layer's colours (default the active layer).", {"layer": STR}, [], lambda a: kr(INVERT, **a)),
   ```
3. New layers: give them `args.get("_new_label", 6)` as colour label (the user's setting, red by default).
   Never change the user's own layers without being asked; read bounds and stacking before replacing a layer.
4. Run `python tools\gen_tools_md.py` and `python tests\test_protocol.py`. Test by hand with Krita running
   (`tests\smoke.py` shows the pattern).

## Why not one combined bridge?
Each app has a different way in: FL Studio only allows MIDI controller scripts, while Krita has a full Python
plugin API. Keeping one small, dependency-free server per app keeps each easy to read and to install. The
shared pattern (MCP over stdio, a plugin inside the app, one `config.json`, red labels for Claude's work) is what
makes them sister projects.
