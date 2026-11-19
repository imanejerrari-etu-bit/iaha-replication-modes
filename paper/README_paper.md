# Article 3 – manuscrit LaTeX (Journal of Systems and Software, classe Elsevier `elsarticle`)

## Compiler
Overleaf : importer le zip, compiler `main.tex` (pdfLaTeX + BibTeX).
Local (TeX Live / MiKTeX) : `pdflatex main && bibtex main && pdflatex main && pdflatex main`.

## Regénérer figures et tableaux
`python make_figures.py` puis `python make_tables.py` (nécessite matplotlib et pandas).
Les figures/tableaux sont construits à partir de `data_summary/*.csv`, dont les valeurs sont COPIÉES des sorties
d'analyse (`analyze_grid.py`, `analyze_rpo.py`, `replay_eval.py`). Pour les barres d'erreur de la figure de la grille,
il faudra une version qui lit `results\grid_results.csv` (non fournie : non testée sur vos données brutes).

## Avant soumission
- Compléter les versions de Python et de scikit-learn (un seul `\todo` reste dans `main.tex`).
- Recompiler, relire, puis `python check_release.py` à la racine du dépôt.
- Tableaux et figures générés par `make_tables.py`, `make_figures.py`, `make_sweep.py`, `make_protection_extra.py` et `pilot/telemetry_summary.py`.

## Client-count sweep
`python make_sweep.py` (from `paper/`) regenerates `tables/sweep.tex` and `figures/fig_sweep.pdf` from `data_summary/client_sweep.csv` (copy of `results/client_sweep.csv`). Raw sweep outputs: `results/client_sweep.csv`, `results/client_sweep_canary.csv`; analysis: `pilot/analyze_client_sweep.py`.
`python make_protection_extra.py` regenerates `tables/crash.tex` and `tables/rate.tex` from `data_summary/rpo_results.csv` and `data_summary/rpo_rate.csv`.
