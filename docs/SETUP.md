# Setup

## 1. The Krita plugin

With **Krita closed**, the installer (or `python install_plugin.py`):
- copies `krita_plugin\claude_bridge\` and `claude_bridge.desktop` to `%APPDATA%\krita\pykrita\`,
- sets `enable_claude_bridge=true` in the `[python]` section of `%LOCALAPPDATA%\kritarc`.

Start Krita. To check: **Settings → Configure Krita → Python Plugin Manager**. "Claude Bridge" should be ticked.
If you ticked it by hand, restart Krita.

**Portable Krita / custom resource folder:** run
`python install_plugin.py --resources "<your resource folder>" [--kritarc "<your kritarc>"]`, or copy the two
items into the `pykrita` folder there and tick the plugin in the Python Plugin Manager.

When the plugin runs, it listens on `127.0.0.1:47821` and writes a fresh token to
`%APPDATA%\krita\claude_bridge_token.txt` each time Krita starts.

## 2. Connect Claude Code

```powershell
python tools\connect_claude.py          # or --print to only show the command
```

That runs `claude mcp add --scope user krita -- <python> <server\server.py>`. Start a **new** Claude Code
session so the tools load. Other MCP clients: run `<python> server/server.py` as a stdio server.

## 3. Try it

Ask Claude: *"Check the Krita connection"* (it calls `krita_status`, or `krita_launch` to start Krita), then
*"make a 1920x1080 canvas and put this picture on it at half size: C:\path\to\photo.jpg"*.

There's also a test script that uses only generated pictures:

```powershell
python tests\smoke.py            # needs Krita running with the plugin
python tests\test_protocol.py    # offline: fake plugin, no Krita needed
python tests\test_doctor.py      # offline: the doctor's diagnosis
```

## 4. Optional: local AI (Ollama)

Install [Ollama](https://ollama.com) and pull a vision model: `ollama pull qwen3-vl:8b-instruct` (about 6 GB).
Then `krita_look` works, and every `krita_cutout` is checked before it's added. The bridge starts Ollama when it's
needed and stops it about 2 minutes after Krita closes, but only if the bridge started it. Change this with
`local_ai.auto_start` / `local_ai.auto_stop_after_app_closed_seconds`, use another model with `vision_model`, or
turn it all off with `local_ai.enabled: false`.

## Troubleshooting

**First, run the doctor:** ask Claude *"run krita_doctor"*, or run `python tools\doctor.py` (add `--deep` to also
test the AI tools' PyTorch, which briefly uses a lot of memory). It checks each link in order and prints the fix
for the first thing that's wrong. It only reads; it starts nothing.

| Symptom | Fix |
|---|---|
| "Krita isn't running with the Claude Bridge plugin (no token file)" | Krita is closed, or the plugin is off: check the Python Plugin Manager. |
| "Can't reach Krita on port 47821" | Another program uses the port, or Krita is still starting. Restart Krita and check the Python Plugin Manager for errors. |
| "bad token" | Krita was restarted while the server kept an old token. Just try again: the server reads the token on every call. |
| `krita_launch` can't find Krita | Set `"krita_exe"` in `%APPDATA%\claude-krita-bridge\config.json`. |
| AI tools say "not set up yet" | They're optional: see [../ai_tools/README.md](../ai_tools/README.md). |

Still stuck? [Open an issue](https://github.com/xoxoFaith1993/claude-krita-bridge/issues/new/choose) with your Krita
version and the error text.
