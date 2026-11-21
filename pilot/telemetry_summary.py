#!/usr/bin/env python3
"""Telemetry summary of the grid for the paper: writes a LaTeX table and a LaTeX sentence.

Usage: python pilot\\telemetry_summary.py [results\\grid_results.csv] [--out paper\\tables]
Outputs: telemetry.tex (table) and telemetry_text.tex (sentence with max lag / errors / deadlocks).
"""
import argparse, os
import numpy as np, pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument("csv", nargs="?", default=os.path.join("results", "grid_results.csv"))
ap.add_argument("--out", default=os.path.join("results", "paper_tables"))
a = ap.parse_args()
df = pd.read_csv(a.csv)
os.makedirs(a.out, exist_ok=True)
need = ["f_cpu_pct", "f_mem_pct", "f_conn_active", "f_lag_mb_max", "f_deadlocks", "f_rollback_rate", "f_tps"]
miss = [c for c in need if c not in df.columns or df[c].isna().all()]
if miss:
    raise SystemExit(f"Missing/empty telemetry columns: {miss}. Nothing written.")

order = ["PERFORMANCE", "CONSISTENCY", "AVAILABILITY", "ECONOMIC"]
tex = {"PERFORMANCE": r"\textsc{performance}", "CONSISTENCY": r"\textsc{consistency}",
       "AVAILABILITY": r"\textsc{availability}", "ECONOMIC": r"\textsc{economic}"}
rows = []
for m in order:
    for wl in ["WRITE", "READMOSTLY", "LOW"]:
        g = df[(df["mode"] == m) & (df["workload"] == wl)]
        if g.empty:
            continue
        by_delay = g.groupby("delay_ms")["f_cpu_pct"].mean()
        cpu = "%.0f" % by_delay.mean() if len(by_delay) == 1 else "%.0f (%.0f--%.0f)" % (by_delay.mean(), by_delay.min(), by_delay.max())
        rows.append(r"%s & \textsc{%s} & %s & %.0f & %.1f \\" % (tex[m], wl.lower(), cpu,
                                                                  g["f_mem_pct"].mean(), g["f_conn_active"].mean()))
    rows.append(r"\addlinespace")
table = (r"\begin{table}[t]" "\n" r"\centering\small" "\n" r"\resizebox{\textwidth}{!}{\begin{tabular}{llccc}" "\n" r"\toprule" "\n"
         r"Mode & Workload & CPU of primary, \% of limit [range over delays] & Memory, \% of limit & Active connections \\" "\n"
         r"\midrule" "\n" + "\n".join(rows[:-1]) + "\n" r"\bottomrule" "\n" r"\end{tabular}}" "\n"
         r"\caption{Telemetry of the primary during the grid (means over repetitions; CPU as a percentage of the one-CPU limit).}"
         "\n" r"\label{tab:telemetry}" "\n" r"\end{table}" "\n")
open(os.path.join(a.out, "telemetry.tex"), "w").write(table)

err = 100.0 * df["f_rollback_rate"] / df["f_tps"].clip(lower=1)
sent = ("Over the whole grid, the replication lag measured on the primary never exceeded %.2f\\,MB (threshold of the cascade: 100\\,MB), "
        "the rollback rate never exceeded %.2f\\%% of transactions (threshold: 1\\%%), and %d deadlocks were recorded (threshold: 5 per window)."
        % (df["f_lag_mb_max"].max(), err.max(), int(df["f_deadlocks"].sum())))
sent += " The first branch of the cascade therefore %s on this testbed." % (
    "never fires" if (df["f_lag_mb_max"].max() <= 100 and err.max() <= 1.0 and df["f_deadlocks"].max() <= 5) else "can fire")
open(os.path.join(a.out, "telemetry_text.tex"), "w").write(sent + "\n")
print(table)
print(sent)
print("\nWritten to", a.out, "- copy both files into paper\\tables\\")
