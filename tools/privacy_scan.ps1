# Privacy scan before publishing: secrets (gitleaks) + personal details (your own patterns).
#   powershell -ExecutionPolicy Bypass -File tools\privacy_scan.ps1 [-Patterns <file>] [-Gitleaks <exe>]
# -Patterns: a text file OUTSIDE the repo with one regex per line (your name, email, user name, drive paths...).
#            Default: %APPDATA%\claude-bridges\private_patterns.txt. Never commit that file.
# Exit code 0 = clean, 1 = something found.
param(
    [string]$Patterns = "$env:APPDATA\claude-bridges\private_patterns.txt",
    [string]$Gitleaks = ""
)
$repo = Split-Path -Parent $PSScriptRoot
$found = 0
$files = Get-ChildItem $repo -Recurse -File | Where-Object {
    $_.FullName -notmatch '\\(\.git|__pycache__|dist|installer\\build)\\' -and $_.Extension -notin '.exe', '.zip', '.png', '.jpg', '.gif'
}

# 1. generic leaks: absolute user paths, e-mail addresses, tokens
$generic = @('[A-Za-z]:\\Users\\(?!you\b|<)[^\\\s"]+', '[\w.+-]+@[\w-]+\.[\w.]+', 'sk-ant-[\w-]{10,}', 'ghp_[A-Za-z0-9]{20,}', 'AIza[0-9A-Za-z_-]{30,}')
$allowEmail = 'noreply@anthropic\.com|users\.noreply\.github\.com|example\.(com|org)'
foreach ($f in $files) {
    $n = 0
    foreach ($line in [IO.File]::ReadAllLines($f.FullName)) {
        $n++
        foreach ($p in $generic) {
            foreach ($m in [regex]::Matches($line, $p)) {
                if ($m.Value -match $allowEmail) { continue }
                Write-Host ("generic  {0}:{1}  {2}" -f $f.FullName.Substring($repo.Length + 1), $n, $m.Value)
                $found++
            }
        }
    }
}

# 2. your own patterns
if (Test-Path $Patterns) {
    $own = Get-Content $Patterns | Where-Object { $_.Trim() -and -not $_.StartsWith('#') }
    foreach ($f in $files) {
        $n = 0
        foreach ($line in [IO.File]::ReadAllLines($f.FullName)) {
            $n++
            foreach ($p in $own) {
                if ($line -match $p) {
                    Write-Host ("personal {0}:{1}  matches pattern #{2}" -f $f.FullName.Substring($repo.Length + 1), $n, ([array]::IndexOf($own, $p) + 1))
                    $found++
                }
            }
        }
        foreach ($p in $own) { if ($f.Name -match $p) { Write-Host "personal file name: $($f.Name)"; $found++ } }
    }
    Write-Host "checked $($own.Count) personal patterns"
} else {
    Write-Host "no personal pattern file at $Patterns (only generic checks ran)"
}

# 3. gitleaks (secrets), if available
if (-not $Gitleaks) { $Gitleaks = (Get-Command gitleaks -ErrorAction SilentlyContinue).Source }
if ($Gitleaks -and (Test-Path $Gitleaks)) {
    & $Gitleaks dir $repo --no-banner --redact
    if ($LASTEXITCODE -ne 0) { $found++ }
    if (Test-Path (Join-Path $repo ".git")) {
        & $Gitleaks git $repo --no-banner --redact
        if ($LASTEXITCODE -ne 0) { $found++ }
    }
} else {
    Write-Host "gitleaks not found (https://github.com/gitleaks/gitleaks) - secret scan skipped"
}

if ($found) { Write-Host "FOUND $found item(s) - fix before publishing"; exit 1 }
Write-Host "privacy scan clean"; exit 0
