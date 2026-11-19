#!/usr/bin/env python3
"""tables/crash.tex and tables/rate.tex from data_summary/rpo_results.csv and data_summary/rpo_rate.csv (run from paper/)."""
import numpy as np, pandas as pd
d = pd.read_csv("data_summary/rpo_results.csv")
t = "\\begin{tabular}{llrrrrrr}\n\\toprule\nScenario & Level & Runs & With loss & Lost (mean) & Unacknowl.\\ rows & Promotion (s) & Writes resume (s) \\\\\n\\midrule\n"
order_lvl = {"ASYNC": 0, "SYNC_1": 1, "SYNC_2": 2}
keys = sorted(d.groupby(["scenario", "level", "isolate_s"]).groups, key=lambda k: (k[0] != "CRASH", k[2], order_lvl[k[1]]))
for (sc, lvl, iso) in keys:
    g = d[(d.scenario == sc) & (d.level == lvl) & (d.isolate_s == iso)]
    if True:
        name = "crash only" if sc == "CRASH" else f"isolation {iso:g}\\,s"
        lvl_t = lvl.replace("_", "\\_")
        pr = f"{g.t_promote_s.min():.1f}--{g.t_promote_s.max():.1f}"
        wr = f"{g.t_write_s.min():.1f}--{g.t_write_s.max():.1f}"
        t += f"{name} & \\textsc{{{lvl_t.lower()}}} & {len(g)} & {(g.lost > 0).sum()} & {g.lost.mean():.0f} & {int(g.extra.sum())} ({int((g.extra > 0).sum())} runs) & {pr} & {wr} \\\\\n"
t += "\\bottomrule\n\\end{tabular}\n"
open("tables/crash.tex", "w").write(t)
r = pd.read_csv("data_summary/rpo_rate.csv"); r["exp"] = r.rate_tps * r.isolate_s
t = "\\begin{tabular}{rrrrrr}\n\\toprule\nRate limit (tps) & Runs & Lost (mean) & Lost (min--max) & Rate $\\times$ 2\\,s & Lost / (rate $\\times$ 2\\,s) \\\\\n\\midrule\n"
for rate, g in r.groupby("rate_tps"):
    t += f"{rate:.0f} & {len(g)} & {g.lost.mean():.0f} & {g.lost.min():.0f}--{g.lost.max():.0f} & {g.exp.iloc[0]:.0f} & {g.lost.mean()/g.exp.iloc[0]:.2f} \\\\\n"
t += "\\bottomrule\n\\end{tabular}\n"
open("tables/rate.tex", "w").write(t)
k, b = np.polyfit(r.exp, r.lost, 1)
print(t); print(f"fit lost = {b:.0f} + {k:.2f} x (rate*T)")
