# run_grid.ps1 - measurement grid (4 modes x network delays x workloads), then summary.
#   .\run_grid.ps1 -Quick   1 repetition, reduced grid (~30-40 min)
#   .\run_grid.ps1          5 repetitions (~6 h, resumable)
param([switch]$Quick)
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "Run .\setup.ps1 first." }

$extra = @()
if ($Quick) { $extra += "--quick" }
& $py pilot\grid_run.py @extra
if ($LASTEXITCODE -ne 0) { throw "grid_run.py failed" }

if ($Quick) { $csv = "results\grid_quick.csv" } else { $csv = "results\grid_results.csv" }
& $py pilot\analyze_grid.py $csv
