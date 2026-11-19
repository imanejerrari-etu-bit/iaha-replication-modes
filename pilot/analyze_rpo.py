#!/usr/bin/env python3
"""Summary of the durability / recovery test."""
import os, sys
import numpy as np, pandas as pd

df = pd.read_csv(sys.argv[1] if len(sys.argv) > 1 else os.path.join("results", "rpo_results.csv"))
rng = np.random.default_rng(42)
if "scenario" not in df.columns:
    df["scenario"] = "CRASH"
if "isolate_s" not in df.columns:
    df["isolate_s"] = 0.0


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def boot(x, n=10000):
    x = np.asarray(x, float)
    return np.percentile(rng.choice(x, size=(n, len(x)), replace=True).mean(axis=1), [2.5, 97.5])


print("=== Durabilite : transactions confirmees au client mais absentes apres le failover ===")
for (sc, iso, lvl), g in df.groupby(["scenario", "isolate_s", "level"], sort=False):
    k = int((g["lost"] > 0).sum()); n = len(g)
    lo, hi = wilson(k, n)
    mlo, mhi = boot(g["lost"])
    print(f"{sc:<7} iso={iso:>3g}s {lvl:<7} | runs={n} | runs avec perte: {k}/{n} (IC Wilson 95% [{lo:.2f}, {hi:.2f}]) | "
          f"perdues: moyenne {g['lost'].mean():.1f} [{mlo:.1f}, {mhi:.1f}], max {int(g['lost'].max())} "
          f"| confirmees/run: {g['acked'].mean():.0f}")
if "extra" in df.columns:
    print("\n=== Lignes presentes mais non confirmees ('extra') ===")
    for (sc, iso, lvl), g in df.groupby(["scenario", "isolate_s", "level"], sort=False):
        e = pd.to_numeric(g["extra"], errors="coerce").dropna()
        print(f"{sc:<7} iso={iso:>3g}s {lvl:<7} | runs avec extra>0: {int((e > 0).sum())}/{len(e)} | total {int(e.sum())} | max {int(e.max()) if len(e) else 0}")
print()
print("=== Reprise : secondes apres la panne (mediane [min-max]) ===")
for (sc, iso, lvl), g in df.groupby(["scenario", "isolate_s", "level"], sort=False):
    def s(col):
        v = pd.to_numeric(g[col], errors="coerce").dropna()
        return f"{v.median():.1f} [{v.min():.1f}-{v.max():.1f}] (n={len(v)})" if len(v) else "n/a"
    nb = int(pd.to_numeric(g["t_write_s"], errors="coerce").isna().sum())
    print(f"{sc:<7} iso={iso:>3g}s {lvl:<7} | promotion: {s('t_promote_s')} | ecriture reprise: {s('t_write_s')} | "
          f"retour spontane a 3 instances: {s('t_full_s')} | ecritures jamais reprises: {nb}/{len(g)} | "
          f"ancien primaire reconstruit: {int(g['recloned'].sum()) if 'recloned' in g else 'n/a'}/{len(g)}")
asy = df[(df["level"] == "ASYNC") & (df["scenario"] == "ISOLATE")]
if asy["isolate_s"].nunique() > 1:
    print("\n=== ASYNC : transactions confirmees perdues en fonction de la duree d'isolement ===")
    t = asy.groupby("isolate_s")["lost"].agg(["count", "mean", "std"]).round(0)
    t["perdues_par_seconde"] = (asy.groupby("isolate_s")["lost"].mean() / asy.groupby("isolate_s")["isolate_s"].first()).round(0)
    print(t.to_string())
print("\nNote : 'lost' = max(0, confirmees - presentes) par client, somme sur les clients.")
print("Avec n petit, rapportez les intervalles (Wilson), pas des p-values.")
