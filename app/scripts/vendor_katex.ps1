# PowerShell equivalent of vendor_katex.sh — use this on Windows.
# Requires Node/npm once; after that everything is offline.

$ErrorActionPreference = "Stop"
$V = "0.16.11"
$ROOT = Split-Path -Parent $PSScriptRoot
$TMP = Join-Path ([System.IO.Path]::GetTempPath()) ([System.IO.Path]::GetRandomFileName())
New-Item -ItemType Directory -Force -Path $TMP | Out-Null

Push-Location $TMP
try {
    npm pack "katex@$V" --silent
    tar -xzf "katex-$V.tgz"
} finally {
    Pop-Location
}

$DEST = Join-Path $ROOT "app\vendor\katex"
New-Item -ItemType Directory -Force -Path $DEST | Out-Null

Copy-Item "$TMP\package\dist\katex.min.css"  $DEST -Force
Copy-Item "$TMP\package\dist\katex.min.js"   $DEST -Force
Copy-Item "$TMP\package\dist\contrib\auto-render.min.js" $DEST -Force
Copy-Item "$TMP\package\dist\fonts" $DEST -Recurse -Force

Remove-Item -Recurse -Force $TMP
Write-Host "KaTeX $V vendored into $DEST"
