#!/usr/bin/env python3
"""Analyse appariee du pilote : CONSISTENCY vs PERFORMANCE, par delai reseau."""
import os, sys
import numpy as np, pandas as pd
from scipy.stats import wilcoxon

df = pd.read_csv(sys.argv[1] if len(sys.argv) > 1 else os.path.join("results", "pilot_results.csv"))
rng = np.random.default_rng(42)


def boot_ci(x, n=10000):
    x = np.asarray(x)
    m = rng.choice(x, size=(n, len(x)), replace=True).mean(axis=1)
    return np.percentile(m, [2.5, 97.5])


print("=== Bruit : coefficient de variation intra-condition (tps) ===")
cv = df.groupby(["delay_ms", "mode"])["tps"].agg(["count", "mean", "std"])
cv["CV_%"] = 100 * cv["std"] / cv["mean"]
print(cv.round(2).to_string(), "\n")

print("=== Controle de validite : le delai ne doit presque pas affecter PERFORMANCE (async) ===")
perf = df[df["mode"] == "PERFORMANCE"].groupby("delay_ms")["tps"].mean()
if len(perf) > 1:
    chg = 100 * (perf.iloc[-1] - perf.iloc[0]) / perf.iloc[0]
    print(f"PERFORMANCE : {perf.iloc[0]:.0f} tps a {perf.index[0]} ms -> {perf.iloc[-1]:.0f} tps a {perf.index[-1]} ms ({chg:+.1f}%)")
    print("OK" if abs(chg) < 10 else "ATTENTION : le delai ralentit aussi le mode asynchrone (>10 %) : le delai touche probablement le trajet client<->primaire.")
print()

print("=== Derive : correlation tps vs ordre global du run (|rho| eleve = derive) ===")
df = df.sort_values(["block", "order"]).reset_index(drop=True)
for d, g in df.groupby("delay_ms"):
    print(f"delai {d} ms : rho de Spearman = {g['tps'].corr(g.index.to_series(), method='spearman'):.2f}")
print()

print("=== Differences appariees par bloc : CONSISTENCY - PERFORMANCE ===")
for d, g in df.groupby("delay_ms"):
    for metric in ("tps", "lat_p95_ms"):
        p = g.pivot(index="block", columns="mode", values=metric).dropna()
        diff = p["CONSISTENCY"] - p["PERFORMANCE"]
        pct = 100 * diff / p["PERFORMANCE"]
        lo, hi = boot_ci(pct)
        try:
            pw = wilcoxon(diff).pvalue
        except ValueError:
            pw = float("nan")
        print(f"delai {d:>2} ms | {metric:<10} | n={len(diff)} | variation moyenne "
              f"{pct.mean():+6.1f}% | IC95% bootstrap [{lo:+.1f}, {hi:+.1f}] | "
              f"Wilcoxon p={pw:.4f} | blocs dans le sens attendu: "
              f"{int((diff < 0).sum() if metric=='tps' else (diff > 0).sum())}/{len(diff)}")
print("\nRappel : avec n blocs, le plus petit p Wilcoxon bilateral est 2/2^n "
      "(n=5 -> 0.0625 : jamais < 0.05). Pour un test, il faut n >= 6.")
