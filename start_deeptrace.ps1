$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Test-HttpEndpoint([string]$url) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 2
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

if (-not (Test-HttpEndpoint 'http://127.0.0.1:8000/health')) {
    Start-Process powershell.exe -WorkingDirectory $root -ArgumentList @(
        '-NoExit',
        '-ExecutionPolicy', 'Bypass',
        '-Command', "Set-Location '$root'; python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --env-file .env"
    )
    Write-Host 'Starting backend on http://127.0.0.1:8000 ...'
} else {
    Write-Host 'Backend already running on http://127.0.0.1:8000'
}

$frontendRunning = (Test-HttpEndpoint 'http://localhost:5173/') -or (Test-HttpEndpoint 'http://localhost:5174/')
if (-not $frontendRunning) {
    Start-Process powershell.exe -WorkingDirectory $root -ArgumentList @(
        '-NoExit',
        '-ExecutionPolicy', 'Bypass',
        '-Command', "Set-Location '$root'; npm run dev"
    )
    Write-Host 'Starting frontend with npm run dev ...'
} else {
    Write-Host 'Frontend already running on port 5173 or 5174'
}

Write-Host ''
Write-Host 'DeepTrace services are launching.'
Write-Host 'Open http://localhost:5173 or http://localhost:5174 if Vite selected the fallback port.'
Start-Process 'http://localhost:5173'
