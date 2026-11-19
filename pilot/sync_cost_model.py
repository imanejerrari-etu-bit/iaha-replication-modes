#!/usr/bin/env python3
"""Closed-loop model of the synchronous-replication cost (WRITE workload, 8 clients, no think time).
Cycle time per transaction L = clients / tps (Little's law). Model: L = L0 + k * RTT, RTT = 2 * one-way delay.
k close to 1 means one network round trip per commit. Uses the grid means (paper/data_summary/grid_means.csv)
or, better, the raw results/grid_results.csv aggregated the same way. Fitting 3 points with 2 parameters leaves
1 degree of freedom: treat k as indicative until more delays / client counts are measured."""
import sys, numpy as np, pandas as pd
CLIENTS = 8
d = pd.read_csv(sys.argv[1] if len(sys.argv) > 1 else "paper/data_summary/grid_means.csv")
w = d[d.workload == "WRITE"].copy()
w["L_ms"] = 1000.0 * CLIENTS / w.tps_w
for m in ["PERFORMANCE", "CONSISTENCY", "AVAILABILITY"]:
    s = w[w["mode"] == m].sort_values("delay_ms")
    rtt = 2 * s.delay_ms.values
    k, l0 = np.polyfit(rtt, s.L_ms.values, 1)
    print(f"{m:<13} L = {l0:5.1f} ms + {k:5.2f} x RTT | residuals (ms): {np.round(s.L_ms.values-(l0+k*rtt),1)}")
