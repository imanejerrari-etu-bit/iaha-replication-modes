#!/usr/bin/env python3
"""Regenerate the paper figures from data_summary/*.csv (values copied from the analysis outputs).
Run from the paper/ folder:  python make_figures.py"""
import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams.update({"font.size": 8, "axes.spines.top": False, "axes.spines.right": False,
                     "pdf.fonttype": 42, "figure.dpi": 150})
COL = {"PERFORMANCE": "#0072B2", "CONSISTENCY": "#D55E00", "AVAILABILITY": "#009E73", "ECONOMIC": "#555555"}
MK = {"PERFORMANCE": "o", "CONSISTENCY": "s", "AVAILABILITY": "^", "ECONOMIC": "D"}
os.makedirs("figures", exist_ok=True)

# ---- Figure 1: grid (throughput and p95 write latency) ----
g = pd.read_csv("data_summary/grid_means.csv")
fig, ax = plt.subplots(2, 3, figsize=(7.2, 4.2), sharex=True)
for j, wl in enumerate(["WRITE", "READMOSTLY", "LOW"]):
    for i, (col, yl) in enumerate([("tps_w", "write throughput (tps)"), ("p95_w_ms", "p95 write latency (ms)")]):
        a = ax[i][j]
        for m in COL:
            d = g[(g.workload == wl) & (g["mode"] == m)].sort_values("delay_ms")
            if d.empty:
                continue
            if m == "ECONOMIC":
                a.axhline(d[col].iloc[0], color=COL[m], ls="--", lw=1, label=m + " (no replica)")
            else:
                a.plot(d.delay_ms, d[col], marker=MK[m], color=COL[m], lw=1.2, ms=4, label=m)
        if i == 1:
            a.axhline(100, color="black", lw=0.8, ls=":")
            a.set_xlabel("emulated one-way delay (ms)")
        a.set_xticks([0, 5, 10])
        if wl == "LOW" and col == "tps_w":
            a.set_ylim(0, 60)          # rate-limited workload: show that throughput is imposed, not noisy
        if j == 0:
            a.set_ylabel(yl)
        if i == 0:
            a.set_title(wl, fontsize=8)
ax[1][2].text(10, 103, "bound 100 ms", ha="right", va="bottom", fontsize=6.5)
h, l = ax[0][0].get_legend_handles_labels()
fig.legend(h, l, loc="lower center", ncol=4, frameon=False, fontsize=7, bbox_to_anchor=(0.5, -0.02))
fig.tight_layout(rect=(0, 0.05, 1, 1))
fig.savefig("figures/fig_grid.pdf", bbox_inches="tight")
plt.close(fig)

# ---- Figure 2: loss versus isolation duration ----
r = pd.read_csv("data_summary/rpo_summary.csv")
fig, ax = plt.subplots(figsize=(3.4, 2.6))
a = r[r.level == "ASYNC"].sort_values("isolate_s")
ax.errorbar(a.isolate_s, a.mean_lost, yerr=[a.mean_lost - a.ci_lo, a.ci_hi - a.mean_lost], fmt="o-",
            color=COL["PERFORMANCE"], capsize=3, lw=1.2, ms=4, label="ASYNC (mean, 95% CI)")
for lv, mk in (("SYNC_1", "^"), ("SYNC_2", "s")):
    s = r[r.level == lv]
    ax.plot(s.isolate_s, s.mean_lost, mk, color=COL["CONSISTENCY" if lv == "SYNC_2" else "AVAILABILITY"],
            ms=5, ls="none", label=f"{lv} (0 lost in all runs)")
ax.set_xlabel("isolation duration (s)")
ax.set_ylabel("acknowledged transactions lost")
ax.set_xticks([1, 2, 5])
ax.legend(frameon=False, fontsize=6.5, loc="upper left")
fig.tight_layout()
fig.savefig("figures/fig_loss.pdf", bbox_inches="tight")
plt.close(fig)

# ---- Figure 3: replay violations by controller and policy ----
p = pd.read_csv("data_summary/replay_summary.csv")
order = ["fixed PERFORMANCE", "fixed CONSISTENCY", "fixed AVAILABILITY", "fixed ECONOMIC", "RULES", "MODEL", "ORACLE"]
pols = ["BALANCED", "DEFAULT", "STRICT"]
pc = {"BALANCED": "#56B4E9", "DEFAULT": "#E69F00", "STRICT": "#CC79A7"}
fig, ax = plt.subplots(figsize=(7.0, 2.7))
w = 0.26
for k, pol in enumerate(pols):
    d = p[p.policy == pol].set_index("controller").loc[order]
    x = [i + (k - 1) * w for i in range(len(order))]
    ax.bar(x, d.viol, width=w, color=pc[pol], label=pol,
           yerr=[d.viol - d.lo, d.hi - d.viol], capsize=1.5, error_kw={"lw": 0.7})
ax.set_xticks(range(len(order)))
ax.set_xticklabels([o.replace("fixed ", "fixed\n") for o in order], fontsize=7)
ax.set_ylabel("steps in violation (%)")
ax.legend(title="declared policy", frameon=False, fontsize=7, title_fontsize=7, ncol=3,
          loc="lower center", bbox_to_anchor=(0.5, 1.0))
ax.set_ylim(0, 108)
fig.tight_layout()
fig.savefig("figures/fig_replay.pdf", bbox_inches="tight")
plt.close(fig)
print("figures written")
