$ErrorActionPreference = "Stop"
$workspaceRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$python = Join-Path $workspaceRoot ".venv\Scripts\python.exe"
$ruff = Join-Path $workspaceRoot ".venv\Scripts\ruff.exe"
$mypy = Join-Path $workspaceRoot ".venv\Scripts\mypy.exe"

function Invoke-NativeChecked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

Push-Location (Join-Path $workspaceRoot "backend")
try {
    Invoke-NativeChecked $python @("-m", "pytest")
    Invoke-NativeChecked $python @("-m", "pytest", "--cov=stock_selector", "--cov-report=term-missing")
    Invoke-NativeChecked $ruff @("check", ".")
    Invoke-NativeChecked $mypy @("src")
} finally {
    Pop-Location
}

Push-Location (Join-Path $workspaceRoot "frontend")
try {
    Invoke-NativeChecked "npm" @("run", "type-check")
    Invoke-NativeChecked "npm" @("run", "lint")
    Invoke-NativeChecked "npm" @("run", "test")
    Invoke-NativeChecked "npm" @("run", "build")
} finally {
    Pop-Location
}
