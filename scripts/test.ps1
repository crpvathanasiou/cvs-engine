Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

poetry run python -m pytest
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
