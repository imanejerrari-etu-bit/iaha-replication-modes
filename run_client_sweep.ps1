# run_client_sweep.ps1 - client-count sweep (2, 8, 32 writers) for PERFORMANCE and CONSISTENCY at 0/5/10 ms.
#   .\run_client_sweep.ps1 -Quick   1 repetition, 0/10 ms, 2 and 32 clients (~20 min)
#   .\run_client_sweep.ps1          5 repetitions (~3 h, resumable)
# Run with the machine plugged in and otherwise idle; do not run it at the same time as another measurement.
param([switch]$Quick)
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "Run .\setup.ps1 first." }
$extra = @()
if ($Quick) { $extra += "--quick" }
& $py pilot\client_sweep.py @extra
if ($LASTEXITCODE -ne 0) { throw "client_sweep.py failed" }
if ($Quick) { $csv = "results\client_sweep_quick.csv" } else { $csv = "results\client_sweep.csv" }
& $py pilot\analyze_client_sweep.py $csv
