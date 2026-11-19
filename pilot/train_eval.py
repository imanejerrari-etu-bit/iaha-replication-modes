#!/usr/bin/env python3
"""Train a RandomForest on telemetry -> measured label and evaluate on UNSEEN conditions.

Folds: leave-one-delay-out (network delay never seen in training) and leave-one-repetition-out.
Baselines: majority class, always-CONSISTENCY, the rule cascade of the earlier papers.
Metrics: accuracy, macro-F1, constraint-violation rate (prediction breaks durability/HA/latency in that
context) and mean cost excess versus the measured best mode.

Usage: python pilot\\train_eval.py [labels.csv] [--policy DEFAULT] [--latency 100]
"""
import argparse, os
import numpy as np, pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score
import label_modes as lm

FEATS = ["f_tps", "f_cpu_pct", "f_mem_pct", "f_conn_active", "f_lag_mb_max", "f_rollback_rate",
         "f_deadlocks", "f_wal_buf_full"]


def evaluate(name, y_true, y_pred, df, cs, policy, L, best_cost):
    viol = np.mean([lm.violates(p, w, d, cs, policy, L) for p, w, d in zip(y_pred, df.workload, df.delay_ms)])
    excess = np.mean([lm.MODE_META[p]["cost"] - best_cost[(w, d)] for p, w, d in zip(y_pred, df.workload, df.delay_ms)])
    return dict(method=name, accuracy=round(accuracy_score(y_true, y_pred), 3),
                macro_F1=round(f1_score(y_true, y_pred, average="macro", zero_division=0), 3),
                violation_rate=round(float(viol), 3), mean_cost_excess=round(float(excess), 2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="?", default=os.path.join("results", "labels.csv"))
    ap.add_argument("--policy", default="DEFAULT", choices=list(lm.POLICIES))
    ap.add_argument("--latency", type=float, default=100.0)
    a = ap.parse_args()
    df = pd.read_csv(a.csv).dropna(subset=FEATS + ["label_measured"]).reset_index(drop=True)
    df["hour"] = df["workload"].map(lm.HOUR)
    cs = lm.cell_stats(df)
    lab = lm.label_table(cs, a.policy, a.latency)
    best_cost = {c: lm.MODE_META[l]["cost"] for c, (l, _) in lab.items()}
    pd.set_option("display.width", 200)

    for use_hour in (True, False):
        feats = FEATS + (["hour"] if use_hour else [])
        print(f"\n##### features: {'with' if use_hour else 'WITHOUT'} hour_of_day #####")
        for fold_name, groups in (("leave-one-delay-out", df["delay_ms"]), ("leave-one-repetition-out", df["rep"])):
            y_all, p_all, idx_all = [], [], []
            for g in sorted(groups.unique()):
                tr, te = df[groups != g], df[groups == g]
                if tr["label_measured"].nunique() < 2:
                    continue
                rf = RandomForestClassifier(n_estimators=200, class_weight="balanced", random_state=42)
                rf.fit(tr[feats], tr["label_measured"])
                p_all += list(rf.predict(te[feats]))
                y_all += list(te["label_measured"])
                idx_all += list(te.index)
            te_all = df.loc[idx_all]
            rows = [evaluate("RandomForest (measured labels)", y_all, p_all, te_all, cs, a.policy, a.latency, best_cost),
                    evaluate("rule cascade (earlier papers)", y_all, list(te_all["label_rules"]), te_all, cs, a.policy, a.latency, best_cost),
                    evaluate("always CONSISTENCY", y_all, ["CONSISTENCY"] * len(y_all), te_all, cs, a.policy, a.latency, best_cost),
                    evaluate("majority class", y_all, [pd.Series(df["label_measured"]).mode()[0]] * len(y_all), te_all, cs, a.policy, a.latency, best_cost)]
            print(f"\n-- {fold_name} (n = {len(y_all)}) --")
            print(pd.DataFrame(rows).to_string(index=False))
    print("\nCaution: leave-one-repetition-out is OPTIMISTIC (the same contexts appear in training in other "
          "repetitions). Leave-one-delay-out is the honest test. 'mean_cost_excess' can be negative when a "
          "method picks a cheaper mode that violates a constraint: read it together with violation_rate.")
    print("\nNote: 'hour_of_day' is a declared mapping (LOW = off-peak), so with it the ECONOMIC class is partly "
          "given away; read the WITHOUT-hour table as the more demanding test.")


if __name__ == "__main__":
    main()
