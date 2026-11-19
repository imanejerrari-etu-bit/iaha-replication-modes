#!/usr/bin/env python3
"""Pre-release check: run from the repository root before `git push` and before submitting the paper.
Fails (exit 1) if raw data are missing, secrets remain, or placeholders are left."""
import glob, os, re, sys
bad = []
for f in ["grid_results.csv", "rpo_results.csv", "pilot_results.csv", "labels.csv"]:
    if not os.path.exists(os.path.join("results", f)):
        bad.append(f"missing raw data: results/{f}")
if not os.path.exists(os.path.join("results", "archive", "environment.txt")):
    bad.append("missing results/archive/environment.txt (software versions)")
skip = {".git", ".venv", "__pycache__"}
for root, dirs, files in os.walk("."):
    dirs[:] = [d for d in dirs if d not in skip]
    for fn in files:
        if not fn.endswith((".txt", ".log", ".md", ".csv", ".tex", ".cff", ".bib", ".yaml", ".ps1")) or fn == "check_release.py":
            continue
        path = os.path.join(root, fn)
        try:
            txt = open(path, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        if fn != "scrub_logs.ps1" and re.search(r"PGPASSWORD=(?!REDACTED)\S+", txt):
            bad.append(f"password left in {path}")
        if re.search(r"GITHUB-USER", txt) or (fn == "main.tex" and re.search(r"\\todo\{[^}]", txt.split("\\begin{document}")[-1])):
            bad.append(f"placeholder left in {path}")
        txt_nomacro = "\n".join(l for l in txt.splitlines() if "\\newcommand" not in l)
        if fn != "README.md" and re.search(r"\[TODO|TODO:", txt_nomacro) and fn != "check_release.py":
            bad.append(f"TODO left in {path}")
        if fn == "README.md" and "[TODO" in txt:
            bad.append(f"TODO left in {path}")
print("\n".join(bad) if bad else "release check OK")
sys.exit(1 if bad else 0)
