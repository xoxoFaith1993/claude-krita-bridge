# Changelog

All notable changes. Versions follow [semantic versioning](https://semver.org/); before 1.0 anything may change.

## [0.1.0] - 2026-11-25
First public release (work in progress).

- Krita plugin "Claude Bridge": a local, token-protected command server inside Krita.
- MCP server with 17 tools: launch, status, new/open/save/export, add picture layers, change layers (move,
  scale, rotate, flip, blend, opacity, labels, stacking, duplicate, delete), masks from images, selections,
  filters, snapshots, bring Krita to the front, `krita_exec`.
- Optional local AI tools: cut out by name (Grounding DINO + SAM 2.1 + BiRefNet), remove objects (LaMa), and
  colour-match cut-outs with a soft shadow.
- One `config.json` (Krita auto-detected, colour label for new layers, AI tools' Python and models).
- Setup.exe (Inno Setup) with bundled embeddable Python; `install_plugin.py`, `tools/connect_claude.py`.
