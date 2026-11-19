# Results

Copy here the measurement files produced by the scripts (not included in the template of this repository):

| File | Produced by |
|---|---|
| `pilot_results.csv` | `run_pilot.ps1` (paired pilot, 8 blocks) |
| `rpo_results.csv` | `run_rpo.ps1` / `pilot\rpo_test.py` (isolation-then-crash, 1, 2 and 5 s) |
| `grid_results.csv` | `run_grid.ps1` (4 modes x delays x workloads, 5 repetitions, telemetry) |
| `labels.csv` | `pilot\label_modes.py` |
| `*.txt` | text outputs of `label_modes.py`, `train_eval.py`, `replay_eval.py`, `rule_sensitivity.py`, `analyze_*.py` |
| `archive\environment.txt` | host and tool versions |

**Before publishing any log, run `..\scrub_logs.ps1`**: tracebacks printed the database password of the throw-away test cluster.
