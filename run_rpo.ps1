# run_rpo.ps1 - durability (RPO) + recovery test, then analysis.
#   .\run_rpo.ps1 -Quick   1 run per level (3 runs, ~25 min)
#   .\run_rpo.ps1          6 repetitions x 3 levels (~2 h)
#   -Scenarios ISOLATE,CRASH   (default ISOLATE)   -IsolateSeconds 2
param([switch]$Quick, [string[]]$Scenarios = @("ISOLATE"), [double]$IsolateSeconds = 2, [string[]]$Levels = @(), [int]$Reps = 0)
$ErrorActionPreference = "Continue"
# powershell -File passes "A,B" as ONE string: split on commas
$Scenarios = @($Scenarios | ForEach-Object { $_ -split "," } | Where-Object { $_ })
$Levels    = @($Levels    | ForEach-Object { $_ -split "," } | Where-Object { $_ })

Set-Location $PSScriptRoot
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "Run .\setup.ps1 first." }

$extra = @()
if ($Quick) { $extra += "--quick" }
$extra += "--scenarios"
$extra += $Scenarios
$extra += "--isolate-s"
$extra += "$IsolateSeconds"
if ($Levels.Count -gt 0) { $extra += "--levels"; $extra += $Levels }
if ($Reps -gt 0) { $extra += "--reps"; $extra += "$Reps" }
& $py pilot\rpo_test.py @extra
if ($LASTEXITCODE -ne 0) { throw "rpo_test.py failed" }

if ($Quick) { $csv = "results\rpo_quick.csv" } else { $csv = "results\rpo_results.csv" }
& $py pilot\analyze_rpo.py $csv
