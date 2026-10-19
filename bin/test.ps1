param([Parameter(ValueFromRemainingArguments=$true)][string[]]$TestArguments)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
docker build --target test -t gazette-mdja-test:local .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
docker run --rm gazette-mdja-test:local @TestArguments
exit $LASTEXITCODE
