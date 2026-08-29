$ErrorActionPreference = "Stop"
$workspaceRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$python = Join-Path $workspaceRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Python virtual environment not found: $python" }
Push-Location $workspaceRoot
try {
    & $python -m uvicorn stock_selector.api.app:app --host 127.0.0.1 --port 8000
} finally {
    Pop-Location
}
