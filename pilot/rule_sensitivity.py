#!/usr/bin/env python3
"""Is the gap between the earlier rule cascade and the measured labels a calibration issue?
Re-run the cascade with rescaled thresholds (grid) and report agreement / violation rate for each setting.
The best setting is chosen IN-SAMPLE: it is an optimistic upper bound for a re-tuned cascade.

Usage: python pilot\\rule_sensitivity.py [labels.csv] [--policy BALANCED] [--latency 100]
"""
import argparse, itertools, os
import numpy as np, pandas as pd
import label_modes as lm


def cascade(row, k, cpu_hi, cpu_lo):
    tps, cpu, lag, dl = row["f_tps"], row["f_cpu_pct"], row["f_lag_mb_max"], row["f_deadlocks"]
    err = 100.0 * row["f_rollback_rate"] / max(tps, 1.0)
    hour = lm.HOUR[row["workload"]]
    if lag > 100 or err > 1.0 or dl > 5:
        return "CONSISTENCY"
    if (hour >= 22 or hour <= 5) and tps < 200 * k:
        return "ECONOMIC"
    if tps > 1200 * k or cpu > cpu_hi:
        return "CONSISTENCY"
    if tps < 500 * k and cpu < cpu_lo and lag < 20:
        return "PERFORMANCE"
    return "CONSISTENCY"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="?", default=os.path.join("results", "labels.csv"))
    ap.add_argument("--policy", default="BALANCED", choices=list(lm.POLICIES))
    ap.add_argument("--latency", type=float, default=100.0)
    a = ap.parse_args()
    df = pd.read_csv(a.csv).dropna(subset=["f_tps", "f_cpu_pct", "f_lag_mb_max", "f_deadlocks", "f_rollback_rate"])
    cs = lm.cell_stats(df)
    lab = lm.label_table(cs, a.policy, a.latency)
    y = np.array([lab[(w, d)][0] for w, d in zip(df.workload, df.delay_ms)])
    rows = []
    for k, ch, cl in itertools.product((1.0, 0.5, 0.25, 0.1), (85, 95, 101), (50, 70, 90)):
        p = np.array([cascade(r, k, ch, cl) for _, r in df.iterrows()])
        viol = np.mean([lm.violates(m, w, d, cs, a.policy, a.latency) for m, w, d in zip(p, df.workload, df.delay_ms)])
        rows.append(dict(tps_scale=k, cpu_hi=ch, cpu_lo=cl, agreement_pct=round(100 * np.mean(p == y), 1),
                         kappa=round(lm.kappa(p, y), 2), violation_pct=round(100 * viol, 1)))
    t = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print("=== Published thresholds (scale 1, cpu 85/50) ===")
    print(t[(t.tps_scale == 1.0) & (t.cpu_hi == 85) & (t.cpu_lo == 50)].to_string(index=False))
    print("\n=== Best recalibrated settings (in-sample, optimistic) ===")
    print(t.sort_values(["agreement_pct", "kappa"], ascending=False).head(5).to_string(index=False))
    print("\n=== Lowest violation rate ===")
    print(t.sort_values(["violation_pct", "agreement_pct"], ascending=[True, False]).head(3).to_string(index=False))
    print("\nIf even the best recalibration stays well below the measured labels, the gap is not only a calibration "
          "issue; if it reaches them, say so: the earlier rules were mis-scaled for this testbed, not wrong in logic.")


if __name__ == "__main__":
    main()
