#!/usr/bin/env python3
"""IAHA measurement grid: for every (mode x network delay x workload) cell, measure throughput,
latency and cost on the testbed, plus IAHA-like telemetry.  The best mode per context is then
derived from MEASUREMENTS (label_modes.py), not from hand-written rules.

Usage:  python pilot\\grid_run.py [--quick]
"""
import argparse, csv, os, random, re, statistics, subprocess, threading, time, datetime
import run_pilot as rp
import rpo_test as rt

K = rp.kubectl
# ---- ASSUMPTION TO CHECK against your IAHA implementation (paper 1, Table 'modes') -------------
MODES = {
    # instances = primary + replicas ; sync = (minSyncReplicas, maxSyncReplicas) ; reads = routing
    "PERFORMANCE":  dict(instances=2, sync=(0, 0), reads="rw"),   # async, 1 replica
    "CONSISTENCY":  dict(instances=3, sync=(2, 2), reads="rw"),   # sync, 2 replicas
    "AVAILABILITY": dict(instances=3, sync=(1, 1), reads="ro"),   # sync + standby reads
    "ECONOMIC":     dict(instances=1, sync=(0, 0), reads="rw"),   # scaled down, no replica
}
GROUPS = {3: ["CONSISTENCY", "AVAILABILITY"], 2: ["PERFORMANCE"], 1: ["ECONOMIC"]}
# writers = tpcb-like (needs write path); readers = select-only. rate = target tps for that process.
WORKLOADS = {
    "WRITE":      dict(w=dict(c=8, rate=None), r=None),
    "READMOSTLY": dict(w=dict(c=2, rate=None), r=dict(c=6, rate=None)),
    "LOW":        dict(w=dict(c=2, rate=40),   r=dict(c=2, rate=60)),
}
CFG = dict(reps=5, delays_ms=[0, 5, 10], workloads=list(WORKLOADS), warmup_s=20, measure_s=60,
           sample_s=6, seed=11, out=os.path.join("results", "grid_results.csv"))
FIELDS = ["rep", "order", "mode", "instances", "delay_ms", "workload", "cost",
          "tps_w", "tps_r", "lat_avg_w_ms", "lat_p95_w_ms", "lat_p99_w_ms", "lat_p95_r_ms", "n_w", "n_r",
          "f_tps", "f_rollback_rate", "f_deadlocks", "f_conn_active", "f_lag_mb_max",
          "f_cpu_pct", "f_mem_pct", "f_wal_buf_full", "timestamp"]


def build_schedule(rng, delays, workloads):
    """One repetition: instance-count groups in random order (scaling is slow), cells shuffled inside."""
    groups = list(GROUPS)
    rng.shuffle(groups)
    sched = []
    for g in groups:
        cells = []
        for mode in GROUPS[g]:
            for d in (delays if mode != "ECONOMIC" else [delays[0]]):   # no replication -> delay irrelevant
                for wl in workloads:
                    cells.append((mode, d, wl))
        rng.shuffle(cells)
        sched += cells
    return sched


def reinit_db():
    """Fresh pgbench tables (no bloat, empty history). Done in async so it can never block on a standby."""
    cur = int(K("get", "cluster", rp.CFG["cluster"], "-o", "jsonpath={.spec.instances}", timeout=30))
    set_sync(0, 0)
    rt.wait_replicas_streaming(420, heal=True, expected=cur - 1)
    print("Re-initialising pgbench tables (fresh, no bloat)...", flush=True)
    rp.pgbench(["-i", "-s", str(rp.CFG["scale"]), "-q"])


def maintenance(vacuum=True):
    """Keep cells comparable: empty pgbench_history, vacuum the big tables."""
    try:
        rp.psql("TRUNCATE pgbench_history", timeout=90)
        if vacuum:
            rp.psql("VACUUM (ANALYZE) pgbench_accounts", timeout=300)
            rp.psql("VACUUM (ANALYZE) pgbench_tellers", timeout=120)
            rp.psql("VACUUM (ANALYZE) pgbench_branches", timeout=120)
    except RuntimeError as e:
        print(f"    maintenance skipped: {str(e)[:100]}", flush=True)


def patch_cluster(spec):
    K("patch", "cluster", rp.CFG["cluster"], "--type", "merge", "-p", spec)


def set_sync(mn, mx):
    patch_cluster('{"spec":{"minSyncReplicas":%d,"maxSyncReplicas":%d}}' % (mn, mx))
    t0 = time.time()
    while time.time() - t0 < 120:
        try:
            if rt.required_sync() == mx:
                return
        except RuntimeError:
            pass
        time.sleep(2)
    raise RuntimeError(f"sync level {mn}/{mx} not applied")


def apply_mode(mode):
    m = MODES[mode]
    cur = int(K("get", "cluster", rp.CFG["cluster"], "-o", "jsonpath={.spec.instances}", timeout=30))
    if cur != m["instances"]:
        set_sync(0, 0)                        # always valid; maxSync must be < instances when scaling down
        patch_cluster('{"spec":{"instances":%d}}' % m["instances"])
        rt.wait_healthy(900, heal=True, n=m["instances"])
        rt.place_client()
    rt.wait_replicas_streaming(420, heal=True, expected=m["instances"] - 1)
    set_sync(*m["sync"])
    rt.wait_replicas_streaming(120, heal=False, expected=m["instances"] - 1)


# ---------------- telemetry (IAHA-like features) ----------------
SQL_TELE = ("SELECT (SELECT xact_commit+xact_rollback FROM pg_stat_database WHERE datname='app'),"
            "(SELECT xact_rollback FROM pg_stat_database WHERE datname='app'),"
            "(SELECT deadlocks FROM pg_stat_database WHERE datname='app'),"
            "(SELECT count(*) FROM pg_stat_activity WHERE state='active' AND datname='app'),"
            "(SELECT coalesce(max(pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn)),0)/1048576.0 FROM pg_stat_replication),"
            "(SELECT wal_buffers_full FROM pg_stat_wal)")


def read_cgroup(pod):
    out = K("exec", pod, "-c", "postgres", "--", "sh", "-c",
            "grep usage_usec /sys/fs/cgroup/cpu.stat; cat /sys/fs/cgroup/memory.current /sys/fs/cgroup/memory.max",
            timeout=30)
    lines = out.split()
    return int(lines[1]), int(lines[2]), (int(lines[3]) if lines[3].isdigit() else None)


def sampler(stop, samples, t_start, pod):
    while not stop.is_set():
        t = time.time()
        try:
            row = [float(x) for x in rp.psql_admin(SQL_TELE, timeout=30).replace("|", ",").split(",")]
            try:
                cpu_us, mem, memmax = read_cgroup(pod)
            except Exception:
                cpu_us, mem, memmax = None, None, None
            samples.append((t - t_start, t, row, cpu_us, mem, memmax))
        except Exception:
            pass
        stop.wait(max(0.5, CFG["sample_s"] - (time.time() - t)))


def summarise_telemetry(samples, warmup):
    s = [x for x in samples if x[0] >= warmup]
    if len(s) < 2:
        return {}
    a, b = s[0], s[-1]
    dt = b[1] - a[1]
    out = {"f_tps": (b[2][0] - a[2][0]) / dt,
           "f_rollback_rate": (b[2][1] - a[2][1]) / dt,
           "f_deadlocks": b[2][2] - a[2][2],
           "f_conn_active": statistics.mean(x[2][3] for x in s),
           "f_lag_mb_max": max(x[2][4] for x in s),
           "f_wal_buf_full": b[2][5] - a[2][5]}
    if a[3] is not None and b[3] is not None:
        out["f_cpu_pct"] = 100.0 * (b[3] - a[3]) / (dt * 1e6)          # % of one core (limit = 1 CPU)
    if b[5]:
        out["f_mem_pct"] = 100.0 * statistics.mean(x[4] for x in s if x[4] is not None) / b[5]
    return {k: round(v, 3) for k, v in out.items()}


# ---------------- load generation ----------------
def pgbench_cmd(host, spec, kind, prefix, total_s):
    args = ["kubectl", f"--context={rp.CFG['context']}", "-n", rp.CFG["namespace"], "exec", rp.CFG["client_pod"],
            "--", "env", f"PGPASSWORD={rp.PW}", "pgbench", "-h", host, "-U", rp.CFG["user"], "-n",
            "-c", str(spec["c"]), "-j", str(spec.get("j", min(2, spec["c"]))), "-T", str(total_s),
            "-l", f"--log-prefix={prefix}"]
    if kind == "r":
        args += ["-S"]
    if spec["rate"]:
        args += ["-R", str(spec["rate"])]
    return args + [rp.CFG["db"]]


def parse_log(raw, warmup):
    rows = []
    for line in raw.splitlines():
        p = line.split()
        if len(p) >= 6:
            rows.append((int(p[4]) + int(p[5]) / 1e6, int(p[2]) / 1000.0))   # (epoch s, latency ms)
    if not rows:
        return 0, 0.0, None, None, None
    t0 = min(r[0] for r in rows)
    kept = [r for r in rows if r[0] >= t0 + warmup]
    if not kept:
        return 0, 0.0, None, None, None
    lat = sorted(r[1] for r in kept)
    span = max(r[0] for r in kept) - (t0 + warmup)
    return len(kept), len(kept) / max(span, 1e-6), statistics.mean(lat), rp.percentile(lat, 0.95), rp.percentile(lat, 0.99)


def run_cell(mode, delay, wl_name, tag):
    m, wl = MODES[mode], WORKLOADS[wl_name]
    rp.set_delay(delay)
    time.sleep(rp.CFG["settle_s"])
    total = CFG["warmup_s"] + CFG["measure_s"]
    host_w = f"{rp.CFG['cluster']}-rw"
    host_r = f"{rp.CFG['cluster']}-ro" if m["reads"] == "ro" else host_w
    procs = {}
    pre = {"w": f"/tmp/g_{tag}_w", "r": f"/tmp/g_{tag}_r"}
    t_start = time.time()
    for kind, host in (("w", host_w), ("r", host_r)):
        spec = wl[kind]
        if spec:
            procs[kind] = subprocess.Popen(pgbench_cmd(host, spec, kind, pre[kind], total),
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stop, samples = threading.Event(), []
    th = threading.Thread(target=sampler, args=(stop, samples, t_start, rp.primary_pod()), daemon=True)
    th.start()
    for p in procs.values():
        p.wait(timeout=total + 120)
    stop.set()
    th.join(timeout=60)
    res = {}
    for kind in procs:
        raw = rp.exec_in_client("sh", "-c", f"cat {pre[kind]}* ; rm -f {pre[kind]}*", timeout=120)
        res[kind] = parse_log(raw, CFG["warmup_s"])
    w = res.get("w", (0, 0.0, None, None, None))
    r = res.get("r", (0, 0.0, None, None, None))
    row = dict(tps_w=round(w[1], 1), tps_r=round(r[1], 1),
               lat_avg_w_ms=round(w[2], 3) if w[2] else "", lat_p95_w_ms=round(w[3], 3) if w[3] else "",
               lat_p99_w_ms=round(w[4], 3) if w[4] else "", lat_p95_r_ms=round(r[3], 3) if r[3] else "",
               n_w=w[0], n_r=r[0])
    row.update(summarise_telemetry(samples, CFG["warmup_s"]))
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--reinit", action="store_true", help="recreate pgbench tables first")
    a = ap.parse_args()
    if a.quick:
        CFG.update(reps=1, delays_ms=[0, 10], workloads=["WRITE", "READMOSTLY"], warmup_s=10, measure_s=30,
                   out=os.path.join("results", "grid_quick.csv"))
    os.makedirs("results", exist_ok=True)
    rp.PW = rp.get_password()
    done = set()
    if os.path.exists(CFG["out"]):
        with open(CFG["out"], newline="") as fh:
            for r in csv.DictReader(fh):
                done.add((int(r["rep"]), r["mode"], int(r["delay_ms"]), r["workload"]))
    new = not os.path.exists(CFG["out"])
    if a.reinit or new:
        reinit_db()
    rng = random.Random(CFG["seed"])
    with open(CFG["out"], "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        if new:
            w.writeheader()
        for rep in range(CFG["reps"]):
            sched = build_schedule(rng, CFG["delays_ms"], CFG["workloads"])
            if any((rep, m, d, w_) not in done for m, d, w_ in sched):
                maintenance(vacuum=True)
            for i, (mode, d, wl) in enumerate(sched):
                if (rep, mode, d, wl) in done:
                    continue
                print(f"[rep {rep+1}/{CFG['reps']}] cell {i+1}/{len(sched)}: {mode} / delay {d} ms / {wl}", flush=True)
                apply_mode(mode)
                maintenance(vacuum=False)
                res = run_cell(mode, d, wl, f"{rep}_{i}")
                w.writerow(dict(rep=rep, order=i, mode=mode, instances=MODES[mode]["instances"], delay_ms=d,
                                workload=wl, cost=MODES[mode]["instances"],
                                timestamp=datetime.datetime.now().isoformat(timespec="seconds"), **res))
                fh.flush()
                print(f"    tps_w={res['tps_w']} tps_r={res['tps_r']} p95_w={res['lat_p95_w_ms']} ms", flush=True)
    print("Done. Results in", CFG["out"])


if __name__ == "__main__":
    try:
        main()
    finally:
        try:
            rp.set_delay(0)
        except Exception:
            pass
