# Claude Krita Bridge

![status: work in progress](https://img.shields.io/badge/status-work%20in%20progress-orange)
![license: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-blue)
![platform: Windows](https://img.shields.io/badge/platform-Windows%2010%2F11-lightgrey)
![MCP server](https://img.shields.io/badge/MCP-server-8A2BE2)

**Let Claude edit your open Krita canvas while you keep painting in it by hand.**

Ask Claude (in [Claude Code](https://claude.com/claude-code) or any MCP app) to build a collage, place and blend
pictures, mask, filter or export. It works live in your running [Krita](https://krita.org) through a small
plugin. Every layer it adds gets a **red colour label**, so its work is easy to tell from yours. It can see the
canvas, your own edits included, at any time.

> **This is a work in progress, and it's never perfect.** It grew out of daily use on one PC. Reports, fixes and
> new tools are very welcome; see [CONTRIBUTING.md](CONTRIBUTING.md).

## What it can do

- **Documents:** new canvas, open images or `.kra` files, save, export flattened (PNG/JPG/WebP/PSD).
- **Layers:** add a picture as a layer (fit, scale, position, opacity, blend mode, above a given layer or inside
  a group); rename, move, scale, rotate, flip, duplicate, re-stack, hide, lock, delete.
- **Masks and selections:** transparency masks from greyscale images; select all, a rectangle or from a file.
- **Filters:** any Krita filter with its settings (blur, unsharp, levels, HSV, desaturate...).
- **See the canvas:** `krita_snapshot` returns a picture of the whole canvas or one layer.
- **A built-in doctor:** `krita_doctor` (or `python tools\doctor.py`) checks every link: Krita, the plugin
  (installed, up to date, switched on), the port and token, an open document, the AI tools' Python and models,
  and the local AI. It says in plain words what's wrong and how to fix it, instead of a tool just failing.
- **Optional local AI (Ollama), fully offline:**
  - Each cut-out is **checked by a local vision model** before it's added. A piece that isn't what you asked
    for ("dog" grabbed the cat) is caught, and nothing is added until you pick the right one.
  - `krita_look` describes the canvas or a layer, including visible problems (hard edges, halos, mismatched
    light).
  - Ollama starts only when needed and stops after Krita closes, and only if the bridge started it.
- **Anything else:** `krita_exec` runs Python inside Krita with its API.
- **Optional AI tools** (your GPU, fully local): **cut out** an object by name ("dog, ball"), **remove** an
  object with content-aware fill, and **match** a pasted cut-out's colours to the scene, with a soft shadow.
  See [ai_tools/README.md](ai_tools/README.md).

All 19 tools: [docs/TOOLS.md](docs/TOOLS.md).

## How it works

```
Claude ──MCP (stdio)──> server/server.py ──JSON over 127.0.0.1:47821 + token──> Krita plugin "Claude Bridge"
       <────────────── results (and PNG snapshots) <──────────────────────────  (runs the code with Krita's API)
```

The plugin starts a tiny local server inside Krita (localhost only, with a fresh secret token each start). The
MCP server sends it Python snippets that run on Krita's own thread. Details and how to add a tool:
[ARCHITECTURE.md](ARCHITECTURE.md).

## What you need

| | |
|---|---|
| Windows 10/11 | the server itself is plain Python and may run elsewhere, but only Windows is tested |
| [Krita](https://krita.org) 5.x (GPL-3.0, free) | tested on 5.3; Python plugins must be available (they are in the official Windows builds) |
| [Claude Code](https://claude.com/claude-code) or another MCP client | |
| Python 3.10+ | bundled by the installer; standard library only |
| *Optional local AI:* [Ollama](https://ollama.com) + a vision model, e.g. `qwen3-vl:8b-instruct` | for `krita_look` and checking cut-outs |
| *Optional AI tools:* Python with PyTorch + about 2.4 GB of models | Apache-2.0 / MIT models, downloaded from their authors, not bundled ([docs/PREREQUISITES.md](docs/PREREQUISITES.md)) |

## Install

### Option 1: Setup.exe

1. **Close Krita.** Download `Claude-Krita-Bridge-Setup-<version>.exe` from
   [Releases](https://github.com/xoxoFaith1993/claude-krita-bridge/releases) and run it (per user, no admin, own Python).
2. Leave both boxes ticked: *install and switch on the Krita plugin* and *register with Claude Code*.
3. Start Krita, then start a new Claude Code session and ask: *"Check the Krita connection."* If anything
   fails, ask *"run the Krita doctor"* (or run `python tools\doctor.py`) for the exact fix.

### Option 2: from source

```powershell
git clone https://github.com/xoxoFaith1993/claude-krita-bridge
cd claude-krita-bridge
python install_plugin.py           # copies the plugin to %APPDATA%\krita\pykrita and enables it (Krita closed)
python tools\connect_claude.py     # claude mcp add --scope user krita -- python server\server.py
```

Portable Krita or a custom resource folder: `python install_plugin.py --resources <folder>`. More in
[docs/SETUP.md](docs/SETUP.md), and building the installer in [docs/BUILDING.md](docs/BUILDING.md).

## Settings

`%APPDATA%\claude-krita-bridge\config.json` (start from [config.example.json](config.example.json)) holds the
`krita.exe` path (auto-detected), the colour label for Claude's layers (6 = red), the snapshot folder, and the
AI tools' Python and model folder. `python server\config.py` prints what's in use.

## Good to know

- **Your edits come first:** when it changes a layer you moved, Claude should read the layer's position and
  stacking first and keep them (the server's instructions tell it so).
- **Security:** the plugin runs Python sent to it, on localhost only, with a token only your Windows user can
  read. See [SECURITY.md](SECURITY.md).
- **Rough edges:** [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md).
- **Not affiliated** with the Krita Foundation or Anthropic.

## Sister project

**[Claude FL Studio Bridge](https://github.com/xoxoFaith1993/claude-fl-studio-bridge)** does the same for FL Studio:
Claude writes notes, drum patterns, mixer changes, automation and renders into your open project. Both bridges
share one pattern: a small server with no dependencies, a plugin inside the app, a single `config.json`, and red
labels on everything Claude adds.

## Contributing

Ideas that would help most: testing on other Krita versions and on macOS/Linux, more tools (text layers,
vector shapes, animation frames), and a video-editing sister bridge. See [CONTRIBUTING.md](CONTRIBUTING.md) and the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Licence

[GPL-3.0](LICENSE), the same as Krita. You can use, study, change and share it. If you share a changed version,
it has to stay open source under the GPL too.
