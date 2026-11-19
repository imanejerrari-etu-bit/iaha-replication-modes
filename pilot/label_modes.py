#!/usr/bin/env python3
"""Derive the best replication mode per context from MEASUREMENTS (not from hand-written rules).

Context = (workload, network delay). A declared requirements policy says, per workload, whether zero data
loss (durable) and high availability (>= 2 instances) are required. The measured label is:
  feasible modes (requirements met AND p95 write latency <= L)  ->  lowest cost  ->  highest throughput
  (modes within `tol` of the best throughput are tied; ties go to the stronger-durability mode).
The requirements policy and L are DECLARED business inputs, not measurements: the article must say so.

Usage: python pilot\\label_modes.py [csv] [--policy DEFAULT|BALANCED|STRICT] [--latency 100]
"""
import argparse, os
import numpy as np, pandas as pd

MODE_META = {"PERFORMANCE": dict(cost=2, durable=False, ha=True),
             "CONSISTENCY": dict(cost=3, durable=True, ha=True),
             "AVAILABILITY": dict(cost=3, durable=True, ha=True),
             "ECONOMIC": dict(cost=1, durable=False, ha=False)}
PREF = ["CONSISTENCY", "AVAILABILITY", "PERFORMANCE", "ECONOMIC"]
POLICIES = {   # workload -> (durable required, HA required)
    "DEFAULT":  {"WRITE": (True, True), "READMOSTLY": (True, True),  "LOW": (False, False)},
    "BALANCED": {"WRITE": (True, True), "READMOSTLY": (False, True), "LOW": (False, False)},
    "STRICT":   {"WRITE": (True, True), "READMOSTLY": (True, True),  "LOW": (True, True)},
}
HOUR = {"LOW": 2, "WRITE": 14, "READMOSTLY": 14}      # LOW stands for off-peak (declared mapping)


def load(path):
    return pd.read_csv(path)


def cell_stats(df, reps_sampler=None):
    """(workload, delay, mode) -> mean tps_w, tps_r, p95_w. ECONOMIC (no replica) is measured at the first
    delay only and broadcast to the other delays (the network delay cannot affect it)."""
    delays = sorted(df["delay_ms"].unique())
    out = {}
    for (wl, d, m), g in df.groupby(["workload", "delay_ms", "mode"]):
        g = g if reps_sampler is None else reps_sampler(g)
        out[(wl, d, m)] = dict(tps_w=g["tps_w"].mean(), tps_r=g["tps_r"].mean(), p95_w=g["lat_p95_w_ms"].mean())
    for (wl, d, m), v in list(out.items()):
        if m == "ECONOMIC":
            for d2 in delays:
                out.setdefault((wl, d2, m), v)
    return out


def select(stats, req, L, rw=0.1, tol=0.05):
    """stats: {mode: dict(tps_w,tps_r,p95_w)} -> (label, infeasible_flag)."""
    def ok_req(m):
        return (not req[0] or MODE_META[m]["durable"]) and (not req[1] or MODE_META[m]["ha"])
    feas = [m for m, s in stats.items() if ok_req(m) and s["p95_w"] <= L]
    if not feas:   # nothing meets the latency SLO: least-bad mode among those meeting the requirements
        cand = [m for m in stats if ok_req(m)] or list(stats)
        return min(cand, key=lambda m: stats[m]["p95_w"]), True
    mincost = min(MODE_META[m]["cost"] for m in feas)
    pool = [m for m in feas if MODE_META[m]["cost"] == mincost]
    score = {m: stats[m]["tps_w"] + rw * stats[m]["tps_r"] for m in pool}
    top = max(score.values())
    tied = [m for m in pool if score[m] >= (1 - tol) * top]
    return next(m for m in PREF if m in tied), False


def contexts(cs):
    return sorted({(wl, d) for (wl, d, _m) in cs})


def label_table(cs, policy, L, rw=0.1, tol=0.05):
    rows = {}
    for wl, d in contexts(cs):
        st = {m: cs[(wl, d, m)] for m in MODE_META if (wl, d, m) in cs}
        rows[(wl, d)] = select(st, POLICIES[policy][wl], L, rw, tol)
    return rows


def violates(mode, wl, d, cs, policy, L):
    """Does predicting `mode` in this context break a hard constraint (durability, HA, latency)?"""
    req = POLICIES[policy][wl]
    m = MODE_META[mode]
    s = cs.get((wl, d, mode))
    if (req[0] and not m["durable"]) or (req[1] and not m["ha"]):
        return True
    return bool(s is not None and s["p95_w"] > L)


def rule_label(row):
    """Rule cascade of the earlier IAHA papers (generate_datasets.py), applied to measured telemetry.
    The 'degraded scenario' branch cannot be observed on this testbed and is omitted."""
    tps, cpu, lag, dl = row["f_tps"], row["f_cpu_pct"], row["f_lag_mb_max"], row["f_deadlocks"]
    err = 100.0 * row["f_rollback_rate"] / max(tps, 1.0)
    hour = HOUR[row["workload"]]
    if lag > 100 or err > 1.0 or dl > 5:
        return "CONSISTENCY"
    if (hour >= 22 or hour <= 5) and tps < 200:
        return "ECONOMIC"
    if tps > 1200 or cpu > 85:
        return "CONSISTENCY"
    if tps < 500 and cpu < 50 and lag < 20:
        return "PERFORMANCE"
    return "CONSISTENCY"


def kappa(a, b):
    a, b = np.asarray(a), np.asarray(b)
    labs = sorted(set(a) | set(b))
    po = np.mean(a == b)
    pe = sum(np.mean(a == l) * np.mean(b == l) for l in labs)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="?", default=os.path.join("results", "grid_results.csv"))
    ap.add_argument("--policy", default="DEFAULT", choices=list(POLICIES))
    ap.add_argument("--latency", type=float, default=100.0)
    ap.add_argument("--boot", type=int, default=300)
    a = ap.parse_args()
    df = load(a.csv)
    pd.set_option("display.width", 200)
    cs = cell_stats(df)
    lab = label_table(cs, a.policy, a.latency)

    print(f"=== Measured labels  (policy {a.policy}: {POLICIES[a.policy]}, p95 write <= {a.latency} ms) ===")
    print(pd.DataFrame([dict(workload=w, delay_ms=d, label=l, infeasible=inf) for (w, d), (l, inf) in lab.items()])
          .to_string(index=False))

    # label confidence under measurement noise (bootstrap over repetitions)
    rng = np.random.default_rng(42)
    counts = {c: {} for c in lab}
    for _ in range(a.boot):
        cs_b = cell_stats(df, lambda g: g.iloc[rng.integers(0, len(g), len(g))])
        for c, (l, _inf) in label_table(cs_b, a.policy, a.latency).items():
            counts[c][l] = counts[c].get(l, 0) + 1
    print("\n=== Label confidence (bootstrap over repetitions) ===")
    for c, d in counts.items():
        top = max(d, key=d.get)
        print(f"{c[0]:<11} {c[1]:>3} ms : {top:<12} {100*d[top]/a.boot:5.1f} %" +
              ("" if len(d) == 1 else "   (others: " + ", ".join(f"{k} {100*v/a.boot:.0f}%" for k, v in d.items() if k != top) + ")"))

    # sensitivity to the declared / tuning parameters
    def stab(**kw):
        alt = label_table(cs, kw.get("policy", a.policy), kw.get("L", a.latency), kw.get("rw", 0.1), kw.get("tol", 0.05))
        return 100.0 * np.mean([alt[c][0] == lab[c][0] for c in lab])
    print("\n=== Sensitivity: % of contexts whose label is unchanged vs the main setting ===")
    print("latency SLO L (ms):", {L: round(stab(L=L)) for L in (50, 75, 100, 150, 200)})
    print("read weight rw    :", {r: round(stab(rw=r)) for r in (0, 0.1, 1)})
    print("tie tolerance     :", {t: round(stab(tol=t)) for t in (0.0, 0.02, 0.05, 0.10)})
    print("requirements policy:", {p: round(stab(policy=p)) for p in POLICIES})

    # rule cascade vs measured label, on measured telemetry
    need = ["f_tps", "f_cpu_pct", "f_lag_mb_max", "f_deadlocks", "f_rollback_rate"]
    if all(c in df.columns for c in need):
        d2 = df.dropna(subset=need).copy()
        d2["label_measured"] = [lab[(w, d)][0] for w, d in zip(d2["workload"], d2["delay_ms"])]
        d2["label_rules"] = d2.apply(rule_label, axis=1)
        d2.to_csv(os.path.join(os.path.dirname(a.csv) or ".", "labels.csv"), index=False)
        print("\n=== Rule cascade (earlier papers) vs measured label, per measured cell ===")
        print(f"agreement: {100*np.mean(d2.label_rules == d2.label_measured):.1f} %   "
              f"Cohen's kappa: {kappa(d2.label_rules, d2.label_measured):.2f}   (n = {len(d2)})")
        print(pd.crosstab(d2["label_measured"], d2["label_rules"], rownames=["measured"], colnames=["rules"]).to_string())
        print("\nby observed mode (the mode the telemetry was measured under):")
        print(d2.groupby("mode").apply(lambda g: f"{100*np.mean(g.label_rules == g.label_measured):.0f} % agreement (n={len(g)})").to_string())
        print("\nSaved: results/labels.csv")
    else:
        print("\nTelemetry columns missing: rule comparison skipped.")


if __name__ == "__main__":
    main()
