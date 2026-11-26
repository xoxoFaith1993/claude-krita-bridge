# Building the installer yourself

## You need
- Windows 10/11 and PowerShell 5.1+
- [Inno Setup 6](https://jrsoftware.org/isinfo.php) (free); or pass `-Iscc <path to ISCC.exe>`
- Internet once: the official embeddable Python from python.org, checked against the SHA-256 pinned in
  `installer/build.ps1`

## Build

```powershell
powershell -ExecutionPolicy Bypass -File installer\build.ps1
```

Output: `dist\Claude-Krita-Bridge-Setup-<version>.exe` and a `.sha256` file. The version is `VERSION` in
`server/server.py`. The script copies an **allow-list** (`server`, `krita_plugin`, `ai_tools`, `tools`, `docs`,
`tests`, README, LICENSE, CHANGELOG, `config.example.json`, `install_plugin.py`) into
`installer\build\stage-krita`, unpacks Python into it and runs ISCC on `installer\claude-krita-bridge.iss`.
To use a newer Python, pass `-PythonVersion` and `-PythonSha256`.

## What the installer does
- installs per user to `%LOCALAPPDATA%\Programs\Claude Krita Bridge` (no admin),
- checkbox: runs `install_plugin.py` (plugin into `%APPDATA%\krita\pykrita`, enabled in `kritarc`),
- checkbox: runs `tools\connect_claude.py` (`claude mcp add`, if `claude` is on PATH),
- doesn't install the optional AI tools (they need PyTorch and about 2.4 GB of models; see `ai_tools/README.md`),
- uninstall removes the plugin, the MCP registration and the files, and keeps your settings folder.

## Test an installer without touching your setup

```powershell
.\dist\Claude-Krita-Bridge-Setup-0.1.0.exe /VERYSILENT /CURRENTUSER /DIR="$env:TEMP\kb-test" /TASKS=""
& "$env:TEMP\kb-test\python\python.exe" "$env:TEMP\kb-test\tests\test_protocol.py"
& "$env:TEMP\kb-test\unins000.exe" /VERYSILENT
```

Note: the uninstaller also runs `install_plugin.py --uninstall` and `connect_claude.py --remove`. On a PC where
you use the bridge for real, test in a separate Windows user or VM, or skip the uninstaller and delete the test
folder by hand.

## Releasing (maintainers)
1. Bump `VERSION` in `server/server.py`, add a `CHANGELOG.md` entry, run `python tools\gen_tools_md.py --check`.
2. `powershell -File tools\privacy_scan.ps1`
3. Build, test-install, then `gh release create vX.Y.Z dist\Claude-Krita-Bridge-Setup-X.Y.Z.exe dist\*.sha256`.
