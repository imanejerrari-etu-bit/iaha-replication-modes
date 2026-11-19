#!/usr/bin/env python3
"""Client-count sweep: table (tables/sweep.tex) and figure (figures/fig_sweep.pdf) from data_summary/client_sweep.csv.
Run from the paper/ folder.  Intervals: percentile bootstrap over the 5 repetitions (2000 resamples)."""
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

rng = np.random.default_rng(7)
d = pd.read_csv("data_summary/client_sweep.csv")
NS, DL = [2, 8, 32], [0, 5, 10]
reps = sorted(d.rep.unique())
tps = d.pivot_table(index=["mode", "clients", "delay_ms"], columns="rep", values="tps_w")
lat = d.pivot_table(index=["mode", "clients", "delay_ms"], columns="rep", values="lat_avg_w_ms")

def loss(rs, n, dl):
    a, b = tps.loc[("CONSISTENCY", n, dl), rs].mean(), tps.loc[("PERFORMANCE", n, dl), rs].mean()
    return 100 * (1 - a / b)

def slope(rs, n):
    y = [lat.loc[("CONSISTENCY", n, dl), rs].mean() for dl in DL]
    k, l0 = np.polyfit([2 * x for x in DL], y, 1)
    return k, l0

def boot(f, B=2000):
    v = [f(list(rng.choice(reps, len(reps)))) for _ in range(B)]
    return np.percentile(v, [2.5, 97.5])

# ---------------- table ----------------
rows = []
for n in NS:
    cells = []
    for dl in DL:
        p = loss(reps, n, dl); lo, hi = boot(lambda rs: loss(rs, n, dl))
        cells.append(f"{p:.0f} [{lo:.0f}, {hi:.0f}]")
    k, l0 = slope(reps, n); klo, khi = boot(lambda rs: slope(rs, n)[0])
    perf = [tps.loc[("PERFORMANCE", n, dl), reps].mean() for dl in DL]
    cpu = d[(d["mode"] == "PERFORMANCE") & (d.clients == n)].f_cpu_pct.mean()
    rows.append((n, cells, k, klo, khi, l0, np.mean(perf), cpu))
    print(n, cells, f"k={k:.2f} [{klo:.2f},{khi:.2f}] L0={l0:.1f} perf_tps={np.mean(perf):.0f} cpu={cpu:.0f}")
t = ("\\begin{tabular}{rcccccc}\n\\toprule\n& \\multicolumn{3}{c}{Throughput loss of \\cons\\ vs \\perf, \\% [95\\% CI]} & & & \\\\\n"
     "\\cmidrule(lr){2-4}\nClients & 0\\,ms & 5\\,ms & 10\\,ms & $k$ [95\\% CI] & $L_0$ (ms) & \\perf\\ CPU (\\%) \\\\\n\\midrule\n")
for n, cells, k, klo, khi, l0, ptps, cpu in rows:
    t += f"{n} & {cells[0]} & {cells[1]} & {cells[2]} & {k:.2f} [{klo:.2f}, {khi:.2f}] & {l0:.1f} & {cpu:.0f} \\\\\n"
t += "\\bottomrule\n\\end{tabular}\n"
open("tables/sweep.tex", "w").write(t)

# sensitivity to the first repetition (lower in some synchronous cells)
r1 = [r for r in reps if r != 0]
print("without rep 0: loss", {(n, dl): round(loss(r1, n, dl), 1) for n in NS for dl in DL}, "k", {n: round(slope(r1, n)[0], 2) for n in NS})

# ---------------- figure ----------------
plt.rcParams.update({"font.size": 8})
fig, ax = plt.subplots(1, 2, figsize=(7.2, 2.9))
col = {2: "#0072B2", 8: "#D55E00", 32: "#009E73"}
for n in NS:
    for m, ls, mk in [("PERFORMANCE", "-", "o"), ("CONSISTENCY", "--", "s")]:
        mu = [tps.loc[(m, n, dl)].mean() for dl in DL]; sd = [tps.loc[(m, n, dl)].std() for dl in DL]
        ax[0].errorbar(DL, mu, yerr=sd, color=col[n], ls=ls, marker=mk, ms=3, capsize=2, lw=1,
                       label=None)
ax[0].set_xlabel("emulated one-way delay (ms)"); ax[0].set_ylabel("write throughput (tps)")
ax[0].set_xticks(DL); ax[0].set_ylim(0, 600)
from matplotlib.lines import Line2D
hs = [Line2D([], [], color=col[n], lw=1, label=f"{n} clients") for n in NS] + \
     [Line2D([], [], color="k", ls="-", marker="o", ms=3, lw=1, label="async (performance)"),
      Line2D([], [], color="k", ls="--", marker="s", ms=3, lw=1, label="sync (consistency)")]
fig.legend(handles=hs, ncol=5, fontsize=6.5, frameon=False, loc="lower center", bbox_to_anchor=(0.5, -0.07))
for n in NS:
    mu = [lat.loc[("CONSISTENCY", n, dl)].mean() for dl in DL]; pf = [lat.loc[("PERFORMANCE", n, dl)].mean() for dl in DL]
    inc = [a - pf[0] for a in mu]       # extra latency of sync, relative to async at 0 ms
    ax[1].plot([2 * x for x in DL], [a - b for a, b in zip(mu, pf)], color=col[n], marker="s", ms=3, lw=1)
x = np.array([0, 20.0]); ax[1].plot(x, x, color="grey", ls=":", lw=1)
ax[1].set_xlabel("round-trip time, RTT (ms)"); ax[1].set_ylabel("sync minus async mean latency (ms)")
ax[1].legend(handles=[Line2D([], [], color="grey", ls=":", lw=1, label="one round trip")], fontsize=6.5, frameon=False, loc="upper left")
fig.tight_layout(); fig.savefig("figures/fig_sweep.pdf", bbox_inches="tight")
