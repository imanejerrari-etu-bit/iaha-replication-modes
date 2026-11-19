# run_pilot.ps1 - run the pilot and analyse it.
#   .\run_pilot.ps1 -Quick     smoke test (2 blocks, 30 s measures, ~15 min)
#   .\run_pilot.ps1            full pilot (8 blocks x 4 conditions, ~1h40)
param([switch]$Quick)
$ErrorActionPreference = "Continue"   # native stderr warnings must not abort; failures are checked via $LASTEXITCODE
Set-Location $PSScriptRoot
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "Run .\setup.ps1 first." }

$extra = @()
if ($Quick) { $extra += "--quick" }
& $py pilot\run_pilot.py @extra
if ($LASTEXITCODE -ne 0) { throw "run_pilot.py failed" }

if ($Quick) { $csv = "results\pilot_quick.csv" } else { $csv = "results\pilot_results.csv" }
& $py pilot\analyze_pilot.py $csv
