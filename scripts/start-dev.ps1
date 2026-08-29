$ErrorActionPreference = "Stop"
$workspaceRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$backendScript = Join-Path $workspaceRoot "scripts\start-backend.ps1"
$frontendScript = Join-Path $workspaceRoot "scripts\start-frontend.ps1"
Start-Process powershell.exe -ArgumentList @("-NoExit", "-File", $backendScript)
Start-Process powershell.exe -ArgumentList @("-NoExit", "-File", $frontendScript)
Write-Host "Backend and frontend terminals started. Close those terminals to stop development services."
