param([switch]$LectureSeule, [switch]$SansPause, [switch]$Lancer)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding
$env:PYTHONIOENCODING = 'utf-8'
try {
    Write-Host 'GAZETTE - Console de controle du pipeline' -ForegroundColor Cyan
    Write-Host 'Prerequis : Docker Desktop et les services du projet demarres.'
    docker info --format '{{.ServerVersion}}' *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Docker est arrete. Demarrer Docker Desktop puis relancer.' }
    docker compose cp bin/voir_pipeline.py airflow-dag-processor:/tmp/gazette_voir_pipeline.py
    if ($LASTEXITCODE -ne 0) {
        throw 'Service Airflow indisponible. Lancer bin/dev.ps1 avant la verification.'
    }
    $taskArguments = @('compose', 'exec')
    if ($SansPause) { $taskArguments += '-T' }
    $taskArguments += @('airflow-dag-processor', 'python', '-u', '/tmp/gazette_voir_pipeline.py')
    if ($LectureSeule) { $taskArguments += '--read-only' }
    if ($SansPause) { $taskArguments += '--no-pause' }
    if ($Lancer) { $taskArguments += '--run' }
    docker @taskArguments
    exit $LASTEXITCODE
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host 'Depuis le dossier du projet : powershell -ExecutionPolicy Bypass -File bin/dev.ps1'
    exit 1
}
