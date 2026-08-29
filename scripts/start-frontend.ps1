$ErrorActionPreference = "Stop"
$workspaceRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$frontendDir = Join-Path $workspaceRoot "frontend"
Push-Location $frontendDir
try {
    & npm.cmd run dev -- --host 127.0.0.1
} finally {
    Pop-Location
}
