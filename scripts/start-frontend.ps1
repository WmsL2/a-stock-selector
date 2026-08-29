$ErrorActionPreference = "Stop"
$workspaceRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$frontendDir = Join-Path $workspaceRoot "frontend"
Push-Location $frontendDir
try {
    npm run dev
} finally {
    Pop-Location
}
