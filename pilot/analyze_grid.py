#!/usr/bin/env python3
"""Summary of the measurement grid: mean (and CV) per mode x delay x workload."""
import os, sys
import pandas as pd

df = pd.read_csv(sys.argv[1] if len(sys.argv) > 1 else os.path.join("results", "grid_results.csv"))
pd.set_option("display.width", 200)
for wl, g in df.groupby("workload"):
    print(f"\n=== Workload {wl} : write tps (mean over reps) / p95 write latency ms ===")
    t = g.pivot_table(index=["mode", "cost"], columns="delay_ms", values="tps_w", aggfunc="mean").round(0)
    l = g.pivot_table(index=["mode", "cost"], columns="delay_ms", values="lat_p95_w_ms", aggfunc="mean").round(1)
    print("tps_w:\n", t.to_string())
    print("p95_w (ms):\n", l.to_string())
    if g["tps_r"].gt(0).any():
        print("tps_r:\n", g.pivot_table(index=["mode", "cost"], columns="delay_ms", values="tps_r", aggfunc="mean").round(0).to_string())
cv = df.groupby(["mode", "delay_ms", "workload"])["tps_w"].agg(["count", "mean", "std"])
cv["CV_%"] = 100 * cv["std"] / cv["mean"]
bad = cv[(cv["count"] > 1) & (cv["CV_%"] > 15)]
print("\n=== Cells with CV > 15 % (noisy, treat with care) ===")
print(bad.round(1).to_string() if len(bad) else "none")
