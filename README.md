# What Replication Modes Cost and Protect - replication package

Scripts, data layout and manuscript for the article *What Replication Modes Cost and Protect: A Measurement
Study of Containerised PostgreSQL and Its Implications for Adaptive Mode Selection* (Jerrari and Assayad).  
Manuscript in preparation. Archived release: Zenodo DOI (added at release).

## What this repository contains
- `k8s/`, `setup.ps1`, `place_client.ps1`, `cleanup.ps1`: a local testbed (kind, 1 control-plane + 3 workers, CloudNativePG v1.22.0, PostgreSQL 16.1, a pgbench client on the primary's node).
- `pilot/`: measurement and analysis scripts (Python).
- `run_pilot.ps1`, `run_rpo.ps1`, `run_grid.ps1`: PowerShell wrappers.
- `results/`: measurement files (see `results/README.md`).
- `paper/`: the LaTeX manuscript, figures and tables (`make_figures.py`, `make_tables.py`).
- `docs/modes.md`: mapping of the four modes to operator parameters.
- `reference_paper2/`: files from the repository of an earlier paper, unchanged (see its `REFERENCE.md`).

## Requirements
Windows 11 with WSL2, Docker Desktop, kind, kubectl, Python 3 (`requirements-pilot.txt`). The reported results were obtained on one laptop
(Intel Core i5-8250U, 16 GB RAM); about 10 GB of memory should be given to WSL2 and more than 20 GB of disk should be free.
Network delay emulation (`tc netem`) needs the kind worker nodes to include `tc`; `setup.ps1` installs it if missing.

## Reproduce
```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1                # testbed, ~15 min
powershell -ExecutionPolicy Bypass -File .\run_pilot.ps1            # paired pilot, ~1h45
powershell -ExecutionPolicy Bypass -File .\run_rpo.ps1              # isolation 2 s, 6 repetitions x 3 levels, ~3 h
.\.venv\Scripts\python.exe pilot\rpo_test.py --scenarios ISOLATE --isolate-s 1 --levels ASYNC SYNC_1 --reps 3
.\.venv\Scripts\python.exe pilot\rpo_test.py --scenarios ISOLATE --isolate-s 5 --levels ASYNC SYNC_1 --reps 3
powershell -ExecutionPolicy Bypass -File .\run_grid.ps1             # 5 repetitions x 30 cells, ~6 h
powershell -ExecutionPolicy Bypass -File .\run_client_sweep.ps1     # 2/8/32 clients, PERFORMANCE vs CONSISTENCY, ~3 h
powershell -ExecutionPolicy Bypass -File .\run_final_experiments.ps1 -Step jobs|rate|crash   # control -j 4, loss vs write rate, crash without isolation
.\.venv\Scripts\python.exe pilot\label_modes.py results\grid_results.csv --policy BALANCED --latency 100
.\.venv\Scripts\python.exe pilot\train_eval.py results\labels.csv --policy BALANCED --latency 100
.\.venv\Scripts\python.exe pilot\replay_eval.py results\labels.csv --policy BALANCED --latency 100
.\.venv\Scripts\python.exe pilot\rule_sensitivity.py results\labels.csv --policy BALANCED --latency 100
.\.venv\Scripts\python.exe pilot\telemetry_summary.py results\grid_results.csv --out paper\tables
```
The scripts resume after an interruption. Run measurements with the machine plugged in and otherwise idle: other workloads change the results.

## Limitations (see the article for the full list)
One host, emulated network delay, three synthetic pgbench workloads, nine contexts, declared (not measured) requirements, no closed-loop evaluation, mode transition costs not measured.

## Licenses
Code: MIT (`LICENSE`). Data: CC BY 4.0 (`LICENSE-DATA.md`).

## Manuscript versions
`paper/` holds the manuscript in the Elsevier `elsarticle` layout. `paper_computing/` is a flat folder (no subfolders) in the Springer one-column layout (`svjour3`, option `smallextended`) built from it by `paper/build_computing.py`; compile `paper_computing/main.tex` with the journal's template files.
