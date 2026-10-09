$backendPath = Join-Path (Split-Path $PSScriptRoot -Parent) "backend"

Push-Location $backendPath
try {
    & uv run uvicorn main:app --reload
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
