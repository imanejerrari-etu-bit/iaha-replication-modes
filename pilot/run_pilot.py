#!/usr/bin/env python3
"""IAHA pilot (Windows / PowerShell friendly, no shell pipelines).

PERFORMANCE (async) vs CONSISTENCY (sync) x emulated network delay.
Random order inside each block; automatic resume if interrupted.

Usage:  python pilot\\run_pilot.py [--quick]
"""
import argparse, base64, csv, os, random, re, statistics, subprocess, sys, time, datetime

CFG = dict(
    context="kind-iaha-pilot", kind_cluster="iaha-pilot",
    cluster="iaha-pg", namespace="default",
    client_pod="pgbench-client", db="app", user="app",
    scale=10, clients=8, jobs=2,
    burnin_s=120, warmup_s=30, measure_s=120, settle_s=10,
    blocks=8, delays_ms=[0, 5], modes=["PERFORMANCE", "CONSISTENCY"],
    seed=42, out=os.path.join("results", "pilot_results.csv"),
)
# Pilot: ONLY synchronous replication changes (instances fixed = 3).
MODES = {
    "PERFORMANCE": dict(minSyncReplicas=0, maxSyncReplicas=0, expect_sync=0),
    "CONSISTENCY": dict(minSyncReplicas=2, maxSyncReplicas=2, expect_sync=2),
}
FIELDS = ["block", "order", "delay_ms", "mode", "tps", "lat_avg_ms", "lat_p95_ms",
          "lat_p99_ms", "n_tx", "mhz_before", "mhz_after", "timestamp"]
NS = CFG["namespace"]
PW = None


def sh(args, check=True, timeout=600):
    try:
        r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Timeout after {timeout}s: {' '.join(map(str, args))[:200]}")
    if check and r.returncode:
        raise RuntimeError(f"Command failed: {' '.join(map(str, args))}\n{r.stderr}")
    return r.stdout.strip()


def kubectl(*a, check=True, timeout=600):
    return sh(["kubectl", f"--context={CFG['context']}", "-n", NS, *a], check=check, timeout=timeout)


def get_password():
    b64 = kubectl("get", "secret", f"{CFG['cluster']}-app", "-o", "jsonpath={.data.password}")
    return base64.b64decode(b64).decode()


def exec_in_client(*cmd, timeout=600):
    return kubectl("exec", CFG["client_pod"], "--", *cmd, timeout=timeout)


def psql(query, timeout=600):
    return exec_in_client("env", f"PGPASSWORD={PW}", "psql", "-h", f"{CFG['cluster']}-rw",
                          "-U", CFG["user"], "-d", CFG["db"], "-tAc", query, timeout=timeout)


def pgbench(args):
    return exec_in_client("env", f"PGPASSWORD={PW}", "pgbench", "-h", f"{CFG['cluster']}-rw",
                          "-U", CFG["user"], *args, CFG["db"])


_WORKERS = None


def worker_nodes():
    """Worker node names are static: read them once (docker/kind can be slow when the host is loaded)."""
    global _WORKERS
    if _WORKERS is None:
        try:
            names = sh(["kind", "get", "nodes", "--name", CFG["kind_cluster"]], timeout=90).split()
        except Exception as e:
            raise RuntimeError("Docker/kind does not answer within 90 s. Restart Docker Desktop "
                               f"and check `docker ps`. ({type(e).__name__})")
        _WORKERS = [n for n in names if "worker" in n]
    return _WORKERS


def set_delay(ms):
    for n in worker_nodes():
        if ms > 0:
            sh(["docker", "exec", n, "tc", "qdisc", "replace", "dev", "eth0", "root",
                "netem", "delay", f"{ms}ms"], timeout=60)
        else:
            sh(["docker", "exec", n, "tc", "qdisc", "del", "dev", "eth0", "root"],
               check=False, timeout=60)


def primary_pod():
    return kubectl("get", "cluster", CFG["cluster"], "-o", "jsonpath={.status.currentPrimary}", timeout=30)


def psql_admin(query, timeout=60):
    """Run SQL as superuser inside the primary pod (local socket).
    Needed because pg_stat_replication hides sync_state from non-superusers."""
    return kubectl("exec", primary_pod(), "-c", "postgres", "--",
                   "psql", "-U", "postgres", "-d", CFG["db"], "-tAc", query, timeout=timeout)


def apply_mode(mode):
    m = MODES[mode]
    patch = '{"spec":{"minSyncReplicas":%d,"maxSyncReplicas":%d}}' % (
        m["minSyncReplicas"], m["maxSyncReplicas"])
    kubectl("patch", "cluster", CFG["cluster"], "--type", "merge", "-p", patch)
    deadline = time.time() + 120
    last = ""
    while time.time() < deadline:
        try:
            n = int(psql_admin("SELECT count(*) FROM pg_stat_replication "
                               "WHERE sync_state IN ('sync','quorum')"))
            last = f"sync standbys seen: {n}"
            if n == m["expect_sync"]:
                return
        except (RuntimeError, ValueError) as e:
            last = str(e)[:300]
        time.sleep(2)
    try:
        diag = psql_admin("SHOW synchronous_standby_names")
    except RuntimeError as e:
        diag = f"(could not query: {str(e)[:200]})"
    raise RuntimeError(f"Mode {mode} not applied after 120 s. Last status: {last}. "
                       f"synchronous_standby_names = {diag}")


def mhz():
    """Host CPU clock (MHz): crude thermal-throttling indicator."""
    try:
        if os.name == "nt":
            out = sh(["powershell", "-NoProfile", "-Command",
                      "(Get-CimInstance Win32_Processor | Measure-Object CurrentClockSpeed -Average).Average"],
                     check=False, timeout=30)
            return round(float(out.replace(",", ".")), 0)
        v = [float(x.split(":")[1]) for x in open("/proc/cpuinfo") if x.startswith("cpu MHz")]
        return round(statistics.mean(v), 0)
    except Exception:
        return ""


def percentile(sorted_vals, p):
    k = (len(sorted_vals) - 1) * p
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def one_run(mode, delay, tag):
    apply_mode(mode)
    set_delay(delay)
    time.sleep(CFG["settle_s"])
    base = ["-c", str(CFG["clients"]), "-j", str(CFG["jobs"])]
    pgbench(base + ["-n", "-T", str(CFG["warmup_s"])])        # warm-up, not measured
    f0 = mhz()
    prefix = f"/tmp/pgb_{tag}"
    out = pgbench(base + ["-n", "-T", str(CFG["measure_s"]), "-l", f"--log-prefix={prefix}"])
    f1 = mhz()
    tps = float(re.search(r"tps = ([\d.]+)", out).group(1))
    raw = exec_in_client("sh", "-c", f"cat {prefix}* ; rm -f {prefix}*")
    lat = sorted(int(l.split()[2]) / 1000.0 for l in raw.splitlines() if l.strip())
    return dict(tps=tps, lat_avg_ms=round(statistics.mean(lat), 3),
                lat_p95_ms=round(percentile(lat, 0.95), 3),
                lat_p99_ms=round(percentile(lat, 0.99), 3),
                n_tx=len(lat), mhz_before=f0, mhz_after=f1)


def main():
    global PW
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="2 blocks, 30 s measures (smoke test)")
    a = ap.parse_args()
    if a.quick:
        CFG.update(blocks=2, measure_s=30, warmup_s=10, burnin_s=20,
                   out=os.path.join("results", "pilot_quick.csv"))
    os.makedirs(os.path.dirname(CFG["out"]), exist_ok=True)
    PW = get_password()
    n_client = kubectl("get", "pod", CFG["client_pod"], "-o", "jsonpath={.spec.nodeName}")
    n_primary = kubectl("get", "pod", primary_pod(), "-o", "jsonpath={.spec.nodeName}")
    if n_client != n_primary:
        raise RuntimeError(f"pgbench client is on {n_client} but the primary is on {n_primary}. "
                           "Run .\\place_client.ps1 first (delay must not affect client<->primary).")
    if psql("SELECT to_regclass('pgbench_accounts') IS NOT NULL") != "t":
        print("Initialising pgbench tables...")
        pgbench(["-i", "-s", str(CFG["scale"]), "-q"])
    done = set()
    if os.path.exists(CFG["out"]):
        with open(CFG["out"], newline="") as fh:
            for r in csv.DictReader(fh):
                done.add((int(r["block"]), int(r["delay_ms"]), r["mode"]))
    new = not os.path.exists(CFG["out"])
    rng = random.Random(CFG["seed"])
    conds = [(d, m) for d in CFG["delays_ms"] for m in CFG["modes"]]
    if new:
        print(f"Burn-in ({CFG['burnin_s']} s, not recorded)...", flush=True)
        apply_mode("PERFORMANCE")
        set_delay(0)
        time.sleep(CFG["settle_s"])
        pgbench(["-c", str(CFG["clients"]), "-j", str(CFG["jobs"]), "-n", "-T", str(CFG["burnin_s"])])
    with open(CFG["out"], "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        if new:
            w.writeheader()
        for b in range(CFG["blocks"]):
            order = conds[:]
            rng.shuffle(order)            # same seed => same order on resume
            for i, (d, m) in enumerate(order):
                if (b, d, m) in done:
                    continue
                print(f"[block {b+1}/{CFG['blocks']}] run {i+1}/{len(order)}: {m}, delay {d} ms",
                      flush=True)
                res = one_run(m, d, f"{b}_{i}")
                w.writerow(dict(block=b, order=i, delay_ms=d, mode=m,
                                timestamp=datetime.datetime.now().isoformat(timespec="seconds"),
                                **res))
                fh.flush()
                print(f"    tps={res['tps']:.0f}  p95={res['lat_p95_ms']} ms", flush=True)
    print("Done. Results in", CFG["out"])


if __name__ == "__main__":
    try:
        main()
    finally:
        try:
            set_delay(0)
        except Exception:
            pass
