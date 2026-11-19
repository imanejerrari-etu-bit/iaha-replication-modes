#!/usr/bin/env python3
"""Analysis of the three final experiments (run from the repository root).
  A. crash without isolation   : results/rpo_results.csv, rows with scenario == CRASH
  B. isolation at limited rate : results/rpo_rate.csv  (loss versus write rate x isolation time)
  C. pgbench threads control   : results/client_sweep_j4.csv versus results/client_sweep.csv (32 clients, -j 4 vs -j 2)
Missing files are skipped."""
import os, numpy as np, pandas as pd

def boot_ci(x, B=2000, seed=3):
    x = np.asarray(x, float)
    if len(x) < 2:
        return (np.nan, np.nan)
    r = np.random.default_rng(seed)
    m = [r.choice(x, len(x)).mean() for _ in range(B)]
    return tuple(np.percentile(m, [2.5, 97.5]))

p = os.path.join("results", "rpo_results.csv")
if os.path.exists(p):
    d = pd.read_csv(p)
    print("=== A. Crash (kill without isolation) vs isolation-then-crash, delay 5 ms ===")
    for (sc, iso, lvl), g in d.groupby(["scenario", "isolate_s", "level"]):
        lost = g.lost.astype(float)
        print(f"{sc:<8} iso={iso:>3g}s {lvl:<7} runs={len(g):>2} runs_with_loss={int((lost>0).sum())}/{len(g)} "
              f"lost mean={lost.mean():8.0f} min={lost.min():6.0f} max={lost.max():6.0f} extra_total={int(g.get('extra', pd.Series([0])).sum())}")
else:
    print("A: results/rpo_results.csv not found")

p = os.path.join("results", "rpo_rate.csv")
if os.path.exists(p):
    d = pd.read_csv(p)
    print("\n=== B. Loss of ASYNC versus write rate (isolation of the primary, then crash) ===")
    d["expected"] = d.rate_tps * d.isolate_s
    for (lvl, rate), g in d.groupby(["level", "rate_tps"]):
        ratio = g.lost / g.expected
        lo, hi = boot_ci(g.lost)
        print(f"{lvl:<7} rate={rate:>5.0f} tps iso={g.isolate_s.iloc[0]:g}s runs={len(g)} lost mean={g.lost.mean():7.0f} "
              f"[{lo:.0f}, {hi:.0f}]  expected rate*T={g.expected.iloc[0]:6.0f}  lost/(rate*T)={ratio.mean():.2f}")
    a = d[d.level == "ASYNC"]
    if a.rate_tps.nunique() >= 2:
        k, b = np.polyfit(a.expected, a.lost, 1)
        print(f"linear fit lost = {b:.0f} + {k:.2f} x (rate*T)   (k close to 1 and b close to 0: loss = write rate x isolation time)")
    base = os.path.join("results", "rpo_results.csv")
    if os.path.exists(base):
        u = pd.read_csv(base)
        u = u[(u.scenario == "ISOLATE") & (u.level == "ASYNC") & (u.isolate_s == 2)]
        if len(u):
            print(f"unlimited rate (earlier runs, 2 s): lost mean = {u.lost.mean():.0f} ({u.lost.mean()/2:.0f} per s)")
else:
    print("\nB: results/rpo_rate.csv not found")

pj, pb = os.path.join("results", "client_sweep_j4.csv"), os.path.join("results", "client_sweep.csv")
if os.path.exists(pj) and os.path.exists(pb):
    j, b = pd.read_csv(pj), pd.read_csv(pb)
    print("\n=== C. 32 clients: pgbench -j 4 (control) versus -j 2 (sweep) ===")
    for (m, dl), g in j.groupby(["mode", "delay_ms"]):
        ref = b[(b["mode"] == m) & (b.clients == 32) & (b.delay_ms == dl)].tps_w
        print(f"{m:<12} {dl:>2} ms  -j4: {g.tps_w.mean():6.1f} tps (n={len(g)}, cpu {g.f_cpu_pct.mean():.0f}%)  |  -j2: {ref.mean():6.1f} tps (n={len(ref)})  ratio {g.tps_w.mean()/ref.mean():.2f}")
    print("ratio ~ 1 -> the load generator does not limit throughput at 32 clients; clearly > 1 -> it does.")
else:
    print("\nC: results/client_sweep_j4.csv or client_sweep.csv not found")
