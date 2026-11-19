#!/usr/bin/env python3
"""Analysis of results/client_sweep.csv: tests the model  L = L0 + k*RTT  (L = mean cycle time per transaction).
1. Little's law check: measured mean latency vs clients/tps.
2. Per mode and client count: fit L = L0 + k*RTT over delays (k ~ 1 means one round trip per commit).
3. Out-of-sample: calibrate (L0, k) for CONSISTENCY on 8 clients, predict tps at the other client counts
   (tps = N / (L0 + k*RTT)); a ratio observed/predicted well below 1 flags saturation (check CPU)."""
import sys, numpy as np, pandas as pd

df = pd.read_csv(sys.argv[1] if len(sys.argv) > 1 else "results/client_sweep.csv")
# --- data-quality checks: completeness per repetition and pauses between cells (sleep/hibernation, interference) ---
print("rows per repetition:", df.groupby("rep").size().to_dict(), "(18 expected per repetition)")
if "timestamp" in df.columns:
    t = df.assign(t=pd.to_datetime(df.timestamp)).sort_values("t")
    gap = t.t.diff().dt.total_seconds() / 60
    for i in t.index[gap > 10]:
        print(f"WARNING: {gap[i]:.0f}-minute pause before cell rep={t.at[i,'rep']} order={t.at[i,'order']} "
              f"({t.at[i,'t']}): cells after it may be unreliable (sleep? other workload?)")
df["rtt"] = 2.0 * df.delay_ms
df["L_little"] = 1000.0 * df.clients / df.tps_w
g = df.groupby(["mode", "clients", "delay_ms", "rtt"]).agg(
    reps=("tps_w", "size"), tps=("tps_w", "mean"), tps_sd=("tps_w", "std"), lat=("lat_avg_w_ms", "mean"),
    L_little=("L_little", "mean"), p95=("lat_p95_w_ms", "mean"), cpu=("f_cpu_pct", "mean")).reset_index()
print("=== cell means ===")
print(g.round(1).to_string(index=False))
print("\n=== 1. Little check: |measured mean latency - clients/tps| / measured (%) ===")
print((100 * (g.lat - g.L_little).abs() / g.lat).describe().round(1)[["mean", "max"]].to_string())

print("\n=== 2. Fit L = L0 + k*RTT (per mode and client count) ===")
fits = {}
for (m, n), s in g.groupby(["mode", "clients"]):
    if s.rtt.nunique() < 2:
        continue
    k, l0 = np.polyfit(s.rtt, s.lat, 1)
    fits[(m, n)] = (l0, k)
    print(f"{m:<12} N={n:<3} L = {l0:6.1f} ms + {k:5.2f} x RTT")

print("\n=== 3. Out-of-sample prediction for CONSISTENCY (calibrated at N=8) ===")
if ("CONSISTENCY", 8) in fits:
    l0, k = fits[("CONSISTENCY", 8)]
    c = g[g["mode"] == "CONSISTENCY"].copy()
    c["tps_pred"] = 1000.0 * c.clients / (l0 + k * c.rtt)
    c["obs/pred"] = c.tps / c.tps_pred
    print(c[["clients", "delay_ms", "tps", "tps_pred", "obs/pred", "cpu"]].round(2).to_string(index=False))
    print("\nReading: obs/pred ~ 1 -> the model transfers across client counts; < 1 at 32 clients with high CPU -> saturation,"
          " not network; > 1 at 2 clients -> L0 shrinks with less contention. State which case holds; do not smooth it away.")
else:
    print("N=8 not in the data; run the full sweep.")
