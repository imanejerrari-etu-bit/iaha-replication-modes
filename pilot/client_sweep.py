#!/usr/bin/env python3
"""Client-count sweep: does the synchronous-replication cost follow  L = L0 + k * RTT  for any number of clients?

Design (reuses the protocol of grid_run.py: same testbed, modes, pgbench transaction, warm-up/measure times,
maintenance, randomised order inside instance-count groups, resumable CSV):
    modes    PERFORMANCE (async, 2 instances), CONSISTENCY (sync, 2 standbys, 3 instances)
    delays   0, 5, 10 ms one-way (RTT = 2 x delay)
    clients  2, 8, 32 writer clients, no rate limit (8 = control that replicates the grid)
    cells    2 modes x 3 delays x 3 client counts = 18 per repetition; 5 repetitions (~3.5 h, resumable)

Usage (from the repository root, after setup.ps1):
    python pilot\\client_sweep.py --dry-run     # print the schedule, touch nothing
    python pilot\\client_sweep.py --quick       # 1 repetition, 0/10 ms, 2 and 32 clients, 30 s (~20 min)
    python pilot\\client_sweep.py               # full sweep -> results\\client_sweep.csv
Then:  python pilot\\analyze_client_sweep.py results\\client_sweep.csv
"""
import argparse, csv, datetime, os, random, sys, time

import grid_run as gr          # same folder; also imports run_pilot (rp) and rpo_test (rt)
import run_pilot as rp

MODES_SWEEP = ["PERFORMANCE", "CONSISTENCY"]          # instance counts 2 and 3
CFG = dict(reps=5, delays_ms=[0, 5, 10], clients=[2, 8, 32], warmup_s=20, measure_s=60, seed=21,
           out=os.path.join("results", "client_sweep.csv"))
FIELDS = ["rep", "order", "mode", "instances", "delay_ms", "clients", "tps_w", "lat_avg_w_ms", "lat_p95_w_ms",
          "lat_p99_w_ms", "n_w", "f_cpu_pct", "f_mem_pct", "f_lag_mb_max", "timestamp"]


def wl_name(n):
    return f"WRITE_C{n}"


def register_workloads(clients, jobs=None):
    for n in clients:      # same write transaction as the grid's WRITE workload, only the client count changes
        w = dict(c=n, rate=None)
        if jobs:
            w["j"] = jobs  # pgbench threads (default of the grid: min(2, clients))
        gr.WORKLOADS[wl_name(n)] = dict(w=w, r=None)
    gr.WORKLOADS["CANARY_C8"] = dict(w=dict(c=8, rate=None), r=None)   # canary always uses the grid's settings


def build_schedule(rng, delays, clients):
    """One repetition: instance-count groups in random order, cells shuffled inside each group."""
    groups = {2: ["PERFORMANCE"], 3: ["CONSISTENCY"]}
    order = list(groups)
    rng.shuffle(order)
    sched = []
    for g in order:
        cells = [(m, d, n) for m in groups[g] if m in MODES_SWEEP for d in delays for n in clients]
        rng.shuffle(cells)
        sched += cells
    return sched


def machine_is_healthy(rep, min_tps):
    """Throughput canary: the same cell as the grid reference. A throttled / sleeping-then-resumed laptop gives ~50%."""
    if min_tps <= 0:
        return True
    for attempt in range(4):
        gr.apply_mode("PERFORMANCE")
        gr.maintenance(vacuum=False)
        res = gr.run_cell("PERFORMANCE", 0, "CANARY_C8", f"canary{rep}_{attempt}")
        tps = float(res["tps_w"])
        with open(os.path.join("results", "client_sweep_canary.csv"), "a") as fh:
            fh.write(f"{datetime.datetime.now().isoformat(timespec='seconds')},{rep},{attempt},{tps}\n")
        print(f"    canary rep {rep+1}: {tps:.0f} tps (threshold {min_tps:.0f})", flush=True)
        if tps >= min_tps:
            return True
        print("    machine below reference speed: check power mode, CPU frequency, background tasks; waiting 5 min", flush=True)
        time.sleep(300)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--jobs", type=int, default=None, help="pgbench threads for the sweep cells (control: 4; default = grid setting)")
    ap.add_argument("--clients", type=int, nargs="+", default=None)
    ap.add_argument("--delays", type=int, nargs="+", default=None)
    ap.add_argument("--reps", type=int, default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--canary-min-tps", type=float, default=420.0,
                    help="before each repetition run PERFORMANCE/0 ms/8 clients; wait and retry if tps is below this "
                         "(healthy machine: 470-530 tps in the grid and reps 0-1; 0 disables the check)")
    a = ap.parse_args()
    if a.quick:
        CFG.update(reps=1, delays_ms=[0, 10], clients=[2, 32], warmup_s=10, measure_s=30,
                   out=os.path.join("results", "client_sweep_quick.csv"))
    if a.clients:
        CFG["clients"] = a.clients
    if a.delays:
        CFG["delays_ms"] = a.delays
    if a.reps:
        CFG["reps"] = a.reps
    if a.out:
        CFG["out"] = a.out
    register_workloads(CFG["clients"], a.jobs)
    gr.CFG.update(warmup_s=CFG["warmup_s"], measure_s=CFG["measure_s"])   # run_cell reads these from grid_run
    rng = random.Random(CFG["seed"])
    if a.dry_run:
        for rep in range(CFG["reps"]):
            s = build_schedule(rng, CFG["delays_ms"], CFG["clients"])
            print(f"rep {rep+1}: {len(s)} cells, e.g. {s[:4]}")
        mins = len(s) * (CFG["warmup_s"] + CFG["measure_s"] + 45) / 60 * CFG["reps"]
        print(f"estimated duration: ~{mins/60:.1f} h")
        return
    os.makedirs("results", exist_ok=True)
    rp.PW = rp.get_password()
    done = set()
    if os.path.exists(CFG["out"]):
        with open(CFG["out"], newline="") as fh:
            for r in csv.DictReader(fh):
                done.add((int(r["rep"]), r["mode"], int(r["delay_ms"]), int(r["clients"])))
    new = not os.path.exists(CFG["out"])
    if new:
        gr.reinit_db()
    with open(CFG["out"], "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        if new:
            w.writeheader()
        for rep in range(CFG["reps"]):
            sched = build_schedule(rng, CFG["delays_ms"], CFG["clients"])
            if any((rep, m, d, n) not in done for m, d, n in sched):
                if not machine_is_healthy(rep, a.canary_min_tps):
                    sys.exit("Stopped: the machine stays below the reference throughput. Fix it and re-run (the CSV is resumable).")
                gr.maintenance(vacuum=True)
            for i, (mode, d, n) in enumerate(sched):
                if (rep, mode, d, n) in done:
                    continue
                print(f"[rep {rep+1}/{CFG['reps']}] cell {i+1}/{len(sched)}: {mode} / {d} ms / {n} clients", flush=True)
                gr.apply_mode(mode)
                gr.maintenance(vacuum=False)
                res = gr.run_cell(mode, d, wl_name(n), f"cs{rep}_{i}")
                row = {k: res.get(k, "") for k in FIELDS if k in res}
                row.update(rep=rep, order=i, mode=mode, instances=gr.MODES[mode]["instances"], delay_ms=d,
                           clients=n, timestamp=datetime.datetime.now().isoformat(timespec="seconds"))
                w.writerow(row)
                fh.flush()
                print(f"    tps_w={res['tps_w']} lat_avg={res['lat_avg_w_ms']} ms cpu={res.get('f_cpu_pct')}%", flush=True)
    print("Done. Results in", CFG["out"])


if __name__ == "__main__":
    try:
        main()
    finally:
        try:
            if not any(x in sys.argv for x in ("--dry-run",)):
                rp.set_delay(0)
        except Exception:
            pass
