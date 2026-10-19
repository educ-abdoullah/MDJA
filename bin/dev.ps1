$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
docker build --target app -t gazette-mdja-app:local .
if ($LASTEXITCODE -ne 0) { throw 'Construction de l application impossible.' }
$projectRoot = (Get-Location).Path
$airflowUid = '50000'
if ($env:OS -ne 'Windows_NT') { $airflowUid = (id -u).Trim() }
$dockerArguments = @('run', '--rm', '--user', '0:0')
if ($env:OS -ne 'Windows_NT') {
    $dockerArguments = @('run', '--rm', '--user', "$($airflowUid):$(id -g)")
}
$dockerArguments += @('--mount', "type=bind,source=$projectRoot,target=/workspace",
    '--entrypoint', 'python', 'gazette-mdja-app:local', '/app/infra/bootstrap.py', '--uid', $airflowUid)
docker @dockerArguments
if ($LASTEXITCODE -ne 0) { throw 'Preparation de .env impossible.' }
docker compose config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Configuration Compose invalide.' }
docker compose build airflow-init
if ($LASTEXITCODE -ne 0) { throw 'Construction Airflow impossible.' }
docker compose up airflow-init --exit-code-from airflow-init
if ($LASTEXITCODE -ne 0) { throw 'Initialisation Airflow impossible.' }
docker compose up -d --wait --wait-timeout 240 postgres airflow-api-server airflow-scheduler airflow-dag-processor
if ($LASTEXITCODE -ne 0) { throw 'Demarrage incomplet : consulter docker compose logs.' }
if ($env:GAZETTE_SKIP_COLLECT -ne '1') {
    docker compose run --rm --no-deps app
    if ($LASTEXITCODE -ne 0) { throw 'Collecte en echec. Consulter sources.csv et la connexion reseau.' }
}
Write-Host 'Airflow : http://localhost:8081 (ou AIRFLOW_PORT dans .env) ; utilisateur : admin'
Write-Host 'Mot de passe : docker compose exec airflow-api-server cat /opt/airflow/auth/passwords.json'
