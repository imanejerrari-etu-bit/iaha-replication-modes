# run_final_experiments.ps1 - the last three experiments (run them one at a time, machine plugged in and idle).
#   .\run_final_experiments.ps1 -Step jobs     control: pgbench -j 4 at 32 clients (about 40 min)
#   .\run_final_experiments.ps1 -Step rate     async loss versus write rate, 2 s isolation (12 runs)
#   .\run_final_experiments.ps1 -Step crash    crash without isolation, 5 repetitions (10 runs)
#   add -Quick for a first check: 1 repetition, one condition
# Every step is resumable: re-run the same command after an interruption.
param([ValidateSet("jobs","rate","crash")][string]$Step, [switch]$Quick)
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw "Run .\setup.ps1 first." }
switch ($Step) {
  "jobs" {
    if ($Quick) { & $py pilot\client_sweep.py --jobs 4 --clients 32 --delays 10 --reps 1 --out results\client_sweep_j4_quick.csv }
    else        { & $py pilot\client_sweep.py --jobs 4 --clients 32 --delays 0 10 --reps 5 --out results\client_sweep_j4.csv }
  }
  "rate" {
    if ($Quick) { & $py pilot\rpo_test.py --scenarios ISOLATE --levels ASYNC --isolate-s 2 --rate 500 --reps 1 --out results\rpo_rate_quick.csv }
    else        { & $py pilot\rpo_test.py --scenarios ISOLATE --levels ASYNC --isolate-s 2 --rate 250 500 1000 --reps 4 }
  }
  "crash" {
    if ($Quick) { & $py pilot\rpo_test.py --scenarios CRASH --levels ASYNC --reps 1 --out results\rpo_crash_quick.csv }
    else        { & $py pilot\rpo_test.py --scenarios CRASH --levels ASYNC SYNC_1 --reps 5 }
  }
}
if ($LASTEXITCODE -ne 0) { throw "step failed" }
& $py pilot\analyze_extra.py
