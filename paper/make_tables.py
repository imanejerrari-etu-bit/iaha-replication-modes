#!/usr/bin/env python3
"""Generate tables/*.tex from data_summary/*.csv (values copied from the analysis outputs). Run: python make_tables.py"""
import pandas as pd

g = pd.read_csv("data_summary/grid_means.csv")
M = ["PERFORMANCE", "CONSISTENCY", "AVAILABILITY", "ECONOMIC"]
lab = {"PERFORMANCE": r"\textsc{perf.}", "CONSISTENCY": r"\textsc{cons.}", "AVAILABILITY": r"\textsc{avail.}", "ECONOMIC": r"\textsc{econ.}"}
rows = []
for m in M:
    for d in ([0, 5, 10] if m != "ECONOMIC" else [0]):
        def v(wl, c, f="{:.0f}"):
            x = g[(g.workload == wl) & (g["mode"] == m) & (g.delay_ms == d)][c].iloc[0]
            return f.format(x)
        cell = [lab[m], str(d) if m != "ECONOMIC" else "0$^{*}$",
                v("WRITE", "tps_w"), v("WRITE", "p95_w_ms", "{:.1f}"),
                v("READMOSTLY", "tps_w"), v("READMOSTLY", "tps_r"), v("READMOSTLY", "p95_w_ms", "{:.1f}"),
                v("LOW", "p95_w_ms", "{:.1f}")]
        rows.append(" & ".join(cell) + r" \\")
    if m != "ECONOMIC":
        rows.append(r"\addlinespace")
t = (r"\begin{tabular}{llrrrrrr}" "\n" r"\toprule" "\n"
     r" & & \multicolumn{2}{c}{\textsc{write}} & \multicolumn{3}{c}{\textsc{readmostly}} & \textsc{low} \\" "\n"
     r"\cmidrule(lr){3-4}\cmidrule(lr){5-7}\cmidrule(lr){8-8}" "\n"
     r"Mode & Delay (ms) & tps$_w$ & p95$_w$ & tps$_w$ & tps$_r$ & p95$_w$ & p95$_w$ \\" "\n" r"\midrule" "\n"
     + "\n".join(rows) + "\n" r"\bottomrule" "\n" r"\end{tabular}" "\n")
open("tables/grid.tex", "w").write(t)

r = pd.read_csv("data_summary/rpo_summary.csv")
out = []
for lv in ["ASYNC", "SYNC_1", "SYNC_2"]:
    for _, x in r[r.level == lv].sort_values("isolate_s").iterrows():
        loss = "%d" % x.runs if lv == "ASYNC" else "0"
        mean = (r"%.0f [%.0f, %.0f]" % (x.mean_lost, x.ci_lo, x.ci_hi)) if lv == "ASYNC" else "0"
        per_s = "%.0f" % (x.mean_lost / x.isolate_s) if lv == "ASYNC" else "0"
        out.append(r"%s & %d & %d & %s/%d & %s & %s & %.1f [%.1f--%.1f] & %.1f \\" % (
            lv.replace("_", r"\_"), x.isolate_s, x.runs, loss, x.runs, mean, per_s,
            x.resume_median_s, x.resume_min_s, x.resume_max_s, x.promote_median_s))
t = (r"\begin{tabular}{lrrrrrrr}" "\n" r"\toprule" "\n"
     r"Level & Isol.\ (s) & Runs & Runs with loss & Lost, mean [95\% CI] & Lost per s & Writes resume (s) & Promotion (s) \\" "\n"
     r"\midrule" "\n" + "\n".join(out) + "\n" r"\bottomrule" "\n" r"\end{tabular}" "\n")
open("tables/rpo.tex", "w").write(t)

p = pd.read_csv("data_summary/replay_summary.csv")
order = ["fixed PERFORMANCE", "fixed CONSISTENCY", "fixed AVAILABILITY", "fixed ECONOMIC", "RULES", "MODEL", "ORACLE"]
names = {"RULES": "Rule cascade [earlier papers]", "MODEL": "Random forest (measured labels)", "ORACLE": "Oracle (measured labels)"}
out = []
for c in order:
    cells = []
    for pol in ["BALANCED", "DEFAULT", "STRICT"]:
        x = p[(p.policy == pol) & (p.controller == c)].iloc[0]
        cells.append("%.1f [%.1f, %.1f]" % (x.viol, x.lo, x.hi))
    b = p[(p.policy == "BALANCED") & (p.controller == c)].iloc[0]
    nm = names.get(c, c.replace("fixed ", "Fixed ").replace("PERFORMANCE", r"\textsc{performance}").replace("CONSISTENCY", r"\textsc{consistency}").replace("AVAILABILITY", r"\textsc{availability}").replace("ECONOMIC", r"\textsc{economic}"))
    out.append(" & ".join([nm] + cells + ["%.2f" % b.cost, "%.1f" % b.trans]) + r" \\")
    if c == "fixed ECONOMIC":
        out.append(r"\midrule")
t = (r"\begin{tabular}{lccccc}" "\n" r"\toprule" "\n"
     r"Controller & \multicolumn{3}{c}{Steps in violation, \% [95\% CI over traces]} & Cost & Switches \\" "\n"
     r"\cmidrule(lr){2-4}" "\n"
     r" & \textsc{balanced} & \textsc{default} & \textsc{strict} & (\textsc{bal.}) & (\textsc{bal.}) \\" "\n"
     r"\midrule" "\n" + "\n".join(out) + "\n" r"\bottomrule" "\n" r"\end{tabular}" "\n")
open("tables/replay.tex", "w").write(t)
print("tables written")
