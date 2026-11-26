# Build the Setup.exe:  powershell -ExecutionPolicy Bypass -File installer\build.ps1
# Needs: Inno Setup 6 (ISCC.exe) and internet once (downloads the official embeddable Python, checked by SHA-256).
# Output: dist\Claude-Krita-Bridge-Setup-<version>.exe. See docs/BUILDING.md.
param(
    [string]$Iscc = "",
    [string]$PythonVersion = "3.14.10",
    [string]$PythonSha256 = "90905E64A840557D8C1BC4F5B74DB3D7EE85E3FFB217611CAC1C7813ACEA4159"
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$repo = Split-Path -Parent $PSScriptRoot
$build = Join-Path $PSScriptRoot "build"
$stage = Join-Path $build "stage-krita"
$version = (Select-String -Path (Join-Path $repo "server\server.py") -Pattern '^VERSION = "(.+)"').Matches[0].Groups[1].Value

# 1. Inno Setup compiler
if (-not $Iscc) {
    $Iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
              "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $Iscc) { throw "Inno Setup 6 not found. Install it from https://jrsoftware.org/isinfo.php or pass -Iscc <path>." }

# 2. embeddable Python (cached in installer\build)
New-Item -ItemType Directory -Force $build | Out-Null
$zip = Join-Path $build "python-$PythonVersion-embed-amd64.zip"
if (-not (Test-Path $zip)) {
    Write-Host "Downloading Python $PythonVersion (embeddable) from python.org..."
    Invoke-WebRequest "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip" -OutFile $zip -UseBasicParsing
}
$hash = (Get-FileHash $zip -Algorithm SHA256).Hash
if ($hash -ne $PythonSha256.ToUpper()) { Remove-Item $zip; throw "Python zip checksum mismatch ($hash). Deleted it; check -PythonSha256." }

# 3. stage the files that ship (an allow-list: nothing personal or generated gets in)
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Force $stage | Out-Null
foreach ($d in "server", "krita_plugin", "ai_tools", "tools", "docs", "tests") {
    Copy-Item (Join-Path $repo $d) (Join-Path $stage $d) -Recurse
}
foreach ($f in "README.md", "LICENSE", "CHANGELOG.md", "config.example.json", "install_plugin.py") {
    Copy-Item (Join-Path $repo $f) $stage
}
Get-ChildItem $stage -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
Expand-Archive $zip (Join-Path $stage "python") -Force

# 4. compile
& $Iscc "/DMyAppVersion=$version" "/DStageDir=$stage" (Join-Path $PSScriptRoot "claude-krita-bridge.iss")
if ($LASTEXITCODE -ne 0) { throw "ISCC failed ($LASTEXITCODE)" }
$out = Join-Path $repo "dist\Claude-Krita-Bridge-Setup-$version.exe"
Write-Host "Built $out"
(Get-FileHash $out -Algorithm SHA256).Hash | Out-File -Encoding ascii "$out.sha256"
