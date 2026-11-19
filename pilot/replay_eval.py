#!/usr/bin/env python3
"""Replay evaluation: judge each controller on what its decisions WOULD HAVE produced, using the measured cells.

A trace is a sequence of contexts (workload, delay). At step t a controller observes the telemetry measured in
context c_t under its PREVIOUS mode, decides d_t, and the outcome is the measured cell (c_t, d_t) of one repetition.
Controllers: 4 fixed modes, the rule cascade of the earlier papers (it can never output AVAILABILITY), a RandomForest (trained on the OTHER repetitions),
and the measured oracle. Outcome metrics: constraint violations (durability / HA / latency), cost, relative throughput,
mode transitions. Mode-transition COSTS were not measured: transitions are only counted.

Usage: python pilot\\replay_eval.py [labels.csv] [--policy BALANCED] [--latency 100] [--traces 300]
"""
import argparse, os
import numpy as np, pandas as pd
from sklearn.ensemble import RandomForestClassifier
import label_modes as lm

FEATS = ["f_tps", "f_cpu_pct", "f_mem_pct", "f_conn_active", "f_lag_mb_max", "f_rollback_rate",
         "f_deadlocks", "f_wal_buf_full"]
WL = ["WRITE", "READMOSTLY", "LOW"]


def make_traces(rng, delays, n, length=24, stay=0.8, dchg=0.1):
    traces = []
    for _ in range(n):
        wl, d = rng.choice(WL), rng.choice(delays)
        t = []
        for _ in range(length):
            if rng.random() > stay:
                wl = rng.choice([w for w in WL if w != wl])
            if rng.random() < dchg:
                d = rng.choice(delays)
            t.append((str(wl), int(d)))
        traces.append(t)
    return traces


def index_rows(df, delays):
    idx = {}
    for _, r in df.iterrows():
        idx[(int(r["rep"]), r["workload"], int(r["delay_ms"]), r["mode"])] = r
    for (rep, wl, d, m), r in list(idx.items()):                 # ECONOMIC measured at one delay only
        if m == "ECONOMIC":
            for d2 in delays:
                idx.setdefault((rep, wl, d2, m), r)
    return idx


def violation_kinds(mode, row, wl, policy, L):
    req = lm.POLICIES[policy][wl]
    meta = lm.MODE_META[mode]
    return (bool(req[0] and not meta["durable"]), bool(req[1] and not meta["ha"]), bool(row["lat_p95_w_ms"] > L))


def run_controller(name, trace, rep, idx, labels, policy, L, rw, rf):
    prev, out = "PERFORMANCE" if name in ("RULES", "MODEL", "ORACLE") else name, []
    for step, (wl, d) in enumerate(trace):
        if name in lm.MODE_META:                                  # fixed mode
            dec = name
        elif name == "ORACLE":
            dec = labels[(wl, d)][0]
        else:
            tele = idx[(rep, wl, d, prev)]                        # observed under the previous mode
            if name == "RULES":
                dec = lm.rule_label(tele)
            else:
                dec = rf.predict(pd.DataFrame([tele[FEATS].astype(float)]))[0]
        row = idx[(rep, wl, d, dec)]
        orc = idx[(rep, wl, d, labels[(wl, d)][0])]
        sc = row["tps_w"] + rw * row["tps_r"]
        so = orc["tps_w"] + rw * orc["tps_r"]
        dur, ha, lat = violation_kinds(dec, row, wl, policy, L)
        out.append(dict(dec=dec, viol=(dur or ha or lat), dur=dur, ha=ha, lat=lat,
                        cost=lm.MODE_META[dec]["cost"], thr=sc / so if so > 0 else np.nan,
                        trans=int(dec != prev), inst=int(lm.MODE_META[dec]["cost"] != lm.MODE_META[prev]["cost"]),
                        agree=int(dec == labels[(wl, d)][0])))
        prev = dec
    return out


def ci(x, rng, n=4000):
    x = np.asarray(x, float)
    b = rng.choice(x, size=(n, len(x)), replace=True).mean(axis=1)
    return np.percentile(b, [2.5, 97.5])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="?", default=os.path.join("results", "labels.csv"))
    ap.add_argument("--policy", default="BALANCED", choices=list(lm.POLICIES))
    ap.add_argument("--latency", type=float, default=100.0)
    ap.add_argument("--rw", type=float, default=0.1)
    ap.add_argument("--traces", type=int, default=300)
    a = ap.parse_args()
    df = pd.read_csv(a.csv).dropna(subset=FEATS).reset_index(drop=True)
    delays = sorted(df["delay_ms"].unique())
    reps = sorted(df["rep"].unique())
    cs = lm.cell_stats(df)
    labels = lm.label_table(cs, a.policy, a.latency)
    idx = index_rows(df, delays)
    rng = np.random.default_rng(42)
    traces = make_traces(rng, delays, a.traces)
    rfs = {}
    for r in reps:                                                # cross-fitting: never train on the replayed repetition
        tr = df[df["rep"] != r]
        lab_r = lm.label_table(lm.cell_stats(tr), a.policy, a.latency)   # labels from the training repetitions only (no leakage)
        lab = [lab_r[(w, d)][0] for w, d in zip(tr["workload"], tr["delay_ms"])]
        rfs[r] = RandomForestClassifier(n_estimators=200, class_weight="balanced", random_state=42).fit(tr[FEATS], lab)

    names = list(lm.MODE_META) + ["RULES", "MODEL", "ORACLE"]
    res = {n: [] for n in names}
    for i, t in enumerate(traces):
        r = reps[i % len(reps)]
        for n in names:
            o = run_controller(n, t, r, idx, labels, a.policy, a.latency, a.rw, rfs[r])
            res[n].append(dict(viol=np.mean([x["viol"] for x in o]), dur=np.mean([x["dur"] for x in o]),
                               ha=np.mean([x["ha"] for x in o]), lat=np.mean([x["lat"] for x in o]),
                               cost=np.mean([x["cost"] for x in o]), thr=np.nanmean([x["thr"] for x in o]),
                               trans=np.sum([x["trans"] for x in o]), inst=np.sum([x["inst"] for x in o]),
                               agree=np.mean([x["agree"] for x in o])))
    rows = []
    for n in names:
        d = pd.DataFrame(res[n])
        lo, hi = ci(d["viol"] * 100, rng)
        rows.append({"controller": n if n in ("RULES", "MODEL", "ORACLE") else f"fixed {n}",
                     "violation_%": f"{100*d.viol.mean():.1f} [{lo:.1f}, {hi:.1f}]",
                     "dur/HA/lat_%": f"{100*d.dur.mean():.0f}/{100*d.ha.mean():.0f}/{100*d.lat.mean():.0f}",
                     "cost": round(d.cost.mean(), 2), "rel_throughput": round(d.thr.mean(), 2),
                     "agree_oracle_%": round(100 * d.agree.mean(), 1),
                     "transitions/trace": round(d.trans.mean(), 1), "instance_changes/trace": round(d.inst.mean(), 1)})
    pd.set_option("display.width", 220)
    print(f"=== Replay of {a.traces} random traces x 24 steps (policy {a.policy}, p95 write <= {a.latency} ms) ===")
    print("violation_% = share of steps breaking durability, HA or latency [95% CI over traces]; "
          "rel_throughput relative to the oracle's mode in the same context.\n")
    print(pd.DataFrame(rows).to_string(index=False))
    print("\nCaveats: transition costs (restarts, re-cloning, warm-up) are NOT measured, only counted; telemetry is observed "
          "under the previous mode; contexts are the 9 measured ones; the model is trained on the other repetitions only.")


if __name__ == "__main__":
    main()
