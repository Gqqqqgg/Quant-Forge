param(
    [int]$Port = 8000
)

$backendPath = Join-Path (Split-Path $PSScriptRoot -Parent) "backend"
Push-Location $backendPath
try {
    & uv run python main.py --port $Port
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
