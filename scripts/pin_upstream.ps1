$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$vendorPath = Join-Path $repoRoot "vendor\F5-TTS"
$pinFile = Join-Path $repoRoot ".upstream-pin"

if (-not (Test-Path $vendorPath)) {
    throw "vendor/F5-TTS not found"
}

git -C $vendorPath fetch --all --tags
git -C $vendorPath pull --ff-only
$pin = (git -C $vendorPath rev-parse HEAD).Trim()
"F5_UPSTREAM_COMMIT=$pin" | Set-Content $pinFile
Write-Host "Pinned F5 upstream commit: $pin"

