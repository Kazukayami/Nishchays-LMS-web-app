$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Write-Host "Starting Employee LMS at http://127.0.0.1:8001"
python -m uvicorn backend.server:app --host 127.0.0.1 --port 8001 --reload
