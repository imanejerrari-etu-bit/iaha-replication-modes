#!/usr/bin/env python3
"""IAHA durability (RPO) + recovery test.

For each run: choose a replication level, write numbered rows with pgbench, SIGKILL-like delete of
the primary pod, then compare ACKNOWLEDGED transactions (pgbench log) with rows present on the new
primary.  lost = rows acknowledged to the client but absent after failover.
Also measures client-visible recovery time (first successful write on the new primary).

Usage:  python pilot\\rpo_test.py [--quick]
"""
import argparse, csv, os, random, re, subprocess, sys, time, datetime
import run_pilot as rp

CFG = dict(reps=6, delays_ms=[5], scenarios=["ISOLATE"], isolate_s=2.0, pre_kill_s=20, write_total_s=120,
           clients=8, jobs=2, probe_timeout_s=300, healthy_timeout_s=900, rejoin_wait_s=240,
           seed=7, out=os.path.join("results", "rpo_results.csv"))
LEVELS = {  # name: (minSyncReplicas, maxSyncReplicas)
    "ASYNC":  (0, 0),
    "SYNC_1": (1, 1),
    "SYNC_2": (2, 2),
}
FIELDS = ["rep", "order", "scenario", "level", "delay_ms", "isolate_s", "killed_pod", "acked", "present", "lost", "extra",
          "t_promote_s", "t_write_s", "t_full_s", "recloned", "timestamp"]
SQL = "INSERT INTO rpo_events(client_id) VALUES (:client_id);\n"
K = rp.kubectl


def cluster_status():
    return K("get", "cluster", rp.CFG["cluster"], "-o",
             "jsonpath={.status.phase}|{.status.readyInstances}|{.status.currentPrimary}", timeout=30)


def heal_replicas():
    """Re-clone any non-primary instance that is not ready (e.g. CrashLoopBackOff after a diverged
    timeline or an abrupt Docker stop). Never touches the primary."""
    prim = rp.primary_pod()
    rows = K("get", "pods", "-l", f"cnpg.io/cluster={rp.CFG['cluster']}", "-o",
             'jsonpath={range .items[*]}{.metadata.name}{" "}{.status.containerStatuses[0].ready}{"\\n"}{end}')
    healed = []
    for line in rows.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] != prim and parts[1] != "true":
            print(f"    healing {parts[0]} (not ready): re-cloning", flush=True)
            reclone(parts[0])
            healed.append(parts[0])
    return healed


def wait_healthy(timeout, heal=False, n=3):
    t0 = time.time()
    healed = False
    while time.time() - t0 < timeout:
        try:
            phase, ready, prim = cluster_status().split("|")
            if phase == "Cluster in healthy state" and ready == str(n):
                return prim, time.time() - t0
        except (RuntimeError, ValueError):
            pass
        if heal and not healed and time.time() - t0 > 150:
            healed = True
            try:
                heal_replicas()
            except RuntimeError:
                pass
        time.sleep(3)
    try:
        pods = K("get", "pods", "-o", "wide", check=False)
    except Exception:
        pods = "(unavailable)"
    raise RuntimeError(f"Cluster not healthy with 3 instances within {timeout:.0f} s.\n{pods}")


def streaming_names():
    out = rp.psql_admin("SELECT application_name FROM pg_stat_replication WHERE state = 'streaming'")
    return set(out.split())


def heal_streaming(action):
    """Replicas that are 'ready' for Kubernetes but not streaming from the primary:
    action='restart' -> graceful pod restart; action='reclone' -> delete pod + PVC (fresh clone)."""
    prim = rp.primary_pod()
    pods = K("get", "pods", "-l", f"cnpg.io/cluster={rp.CFG['cluster']}", "-o",
             "jsonpath={.items[*].metadata.name}", timeout=30).split()
    ok = streaming_names()
    for pod in pods:
        if pod != prim and pod not in ok:
            print(f"    {pod} is not streaming: {action}", flush=True)
            if action == "restart":
                K("delete", "pod", pod, "--wait=false", check=False)
            else:
                reclone(pod)


def wait_replicas_streaming(timeout, heal=False, expected=2):
    """'3 ready instances' is NOT enough: a replica can be ready without streaming.
    Wait until both replicas stream and are within 1 MiB of the primary.
    With heal=True: restart non-streaming replicas after 90 s, re-clone them after 210 s."""
    if expected == 0:
        return
    t0 = time.time()
    last = ""
    stage = 0
    while time.time() - t0 < timeout:
        try:
            out = rp.psql_admin("SELECT count(*) FILTER (WHERE state = 'streaming' AND "
                                "pg_wal_lsn_diff(sent_lsn, replay_lsn) < 1048576) "
                                "FROM pg_stat_replication")
            last = out
            if int(out) == expected:
                return
        except (RuntimeError, ValueError) as e:
            last = str(e)[:200]
        el = time.time() - t0
        try:
            if heal and stage == 0 and el > 90:
                stage = 1
                heal_streaming("restart")
            elif heal and stage == 1 and el > 210:
                stage = 2
                heal_streaming("reclone")
        except RuntimeError as e:
            print(f"    heal attempt failed: {str(e)[:120]}", flush=True)
        time.sleep(3)
    raise RuntimeError(f"Replicas not streaming and caught up within {timeout} s (last: {last})")


def reclone(pod):
    """Delete a diverged old primary together with its PVC: CNPG re-clones a fresh replica
    from the new primary (more deterministic than waiting for pg_rewind)."""
    K("delete", "pvc", pod, "--wait=false", check=False)
    K("delete", "pod", pod, "--grace-period=0", "--force", check=False)


def place_client():
    """(Re)create pgbench client on the node of the CURRENT primary."""
    prim = rp.primary_pod()
    node = K("get", "pod", prim, "-o", "jsonpath={.spec.nodeName}")
    K("delete", "pod", rp.CFG["client_pod"], "--ignore-not-found", "--wait=true")
    tpl = open(os.path.join("k8s", "pgbench-client.yaml")).read().replace("__NODE__", node)
    r = subprocess.run(["kubectl", f"--context={rp.CFG['context']}", "apply", "-f", "-"],
                       input=tpl, text=True, capture_output=True)
    if r.returncode:
        raise RuntimeError(r.stderr)
    K("wait", "--for=condition=Ready", f"pod/{rp.CFG['client_pod']}", "--timeout=180s")


def required_sync():
    names = rp.psql_admin("SHOW synchronous_standby_names").strip()
    m = re.search(r"(?:ANY|FIRST)\s+(\d+)", names)
    return int(m.group(1)) if m else (1 if names else 0)


def apply_level(level):
    mn, mx = LEVELS[level]
    K("patch", "cluster", rp.CFG["cluster"], "--type", "merge", "-p",
      '{"spec":{"minSyncReplicas":%d,"maxSyncReplicas":%d}}' % (mn, mx))
    t0 = time.time()
    while time.time() - t0 < 120:
        try:
            if required_sync() == mx:
                return
        except RuntimeError:
            pass
        time.sleep(2)
    raise RuntimeError(f"Level {level} not applied")


def probe_write():
    """One write attempt through the -rw service; never blocks longer than ~25 s."""
    try:
        rp.sh(["kubectl", f"--context={rp.CFG['context']}", "-n", rp.CFG["namespace"], "exec",
               rp.CFG["client_pod"], "--", "env", f"PGPASSWORD={rp.PW}",
               "PGOPTIONS=-c statement_timeout=4000", "PGCONNECT_TIMEOUT=3", "psql",
               "-h", f"{rp.CFG['cluster']}-rw", "-U", rp.CFG["user"], "-d", rp.CFG["db"], "-tAc",
               "INSERT INTO rpo_events(client_id) VALUES (-1)"], timeout=25)
        return True
    except RuntimeError:
        return False


def one_run(rep, order, level, delay, scenario, rate=None):
    wait_healthy(CFG["healthy_timeout_s"], heal=True)
    place_client()
    rp.set_delay(delay)
    apply_level("ASYNC")                      # setup writes must never block on a missing standby
    wait_replicas_streaming(420, heal=True)
    rp.psql("CREATE TABLE IF NOT EXISTS rpo_events(id bigserial PRIMARY KEY, client_id int NOT NULL)",
            timeout=90)
    rp.psql("TRUNCATE rpo_events RESTART IDENTITY", timeout=90)
    wait_replicas_streaming(120)              # replicas have replayed the TRUNCATE
    apply_level(level)
    time.sleep(5)
    subprocess.run(["kubectl", f"--context={rp.CFG['context']}", "-n", rp.CFG["namespace"], "exec", "-i",
                    rp.CFG["client_pod"], "--", "sh", "-c", "cat > /tmp/rpo.sql"],
                   input=SQL, text=True, check=True, capture_output=True)
    prefix = f"/tmp/rpo_{rep}_{order}"
    bench = subprocess.Popen(
        ["kubectl", f"--context={rp.CFG['context']}", "-n", rp.CFG["namespace"], "exec", rp.CFG["client_pod"],
         "--", "env", f"PGPASSWORD={rp.PW}", "pgbench", "-h", f"{rp.CFG['cluster']}-rw", "-U", rp.CFG["user"],
         "-n", "-f", "/tmp/rpo.sql", "-c", str(CFG["clients"]), "-j", str(CFG["jobs"]),
         "-T", str(CFG["write_total_s"]), "-l", f"--log-prefix={prefix}"] + (["-R", str(rate)] if rate else []) + [rp.CFG["db"]],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(CFG["pre_kill_s"])
    old_primary = rp.primary_pod()
    if scenario == "ISOLATE":
        # Primary loses its network (replication stream blocked), keeps acknowledging local clients
        # in async mode, then dies while still isolated: unsent WAL is lost with it.
        pnode = K("get", "pod", old_primary, "-o", "jsonpath={.spec.nodeName}")
        rp.sh(["docker", "exec", pnode, "tc", "qdisc", "replace", "dev", "eth0", "root",
               "netem", "loss", "100%"], timeout=60)
        time.sleep(CFG["isolate_s"])
        # kill postgres locally (no network needed), THEN give the network back
        rp.sh(["docker", "exec", pnode, "sh", "-c",
               "crictl stop -t 0 $(crictl ps --name postgres -q)"], check=False, timeout=60)
        t_kill = time.time()
        rp.set_delay(delay)
        K("delete", "pod", old_primary, "--grace-period=0", "--force", check=False)
    else:
        t_kill = time.time()
        K("delete", "pod", old_primary, "--grace-period=0", "--force", check=False)
    # promotion detected
    t_promote = None
    while time.time() - t_kill < CFG["probe_timeout_s"]:
        try:
            if rp.primary_pod() != old_primary:
                t_promote = time.time() - t_kill
                break
        except RuntimeError:
            pass
        time.sleep(0.5)
    # first successful client write
    t_write = None
    while time.time() - t_kill < CFG["probe_timeout_s"]:
        if probe_write():
            t_write = time.time() - t_kill
            break
        time.sleep(1)
    if t_write is None:
        try:
            print("    WARNING: writes did not resume within "
                  f"{CFG['probe_timeout_s']} s. synchronous_standby_names = "
                  f"{rp.psql_admin('SHOW synchronous_standby_names')} | replication = "
                  f"{rp.psql_admin('SELECT application_name, state, sync_state FROM pg_stat_replication')}",
                  flush=True)
        except RuntimeError as e:
            print(f"    WARNING: writes did not resume; diagnostics unavailable ({str(e)[:120]})", flush=True)
    try:
        bench.wait(timeout=60)
    except subprocess.TimeoutExpired:
        rp.exec_in_client("sh", "-c", "pkill pgbench || true")
        bench.kill()
    # acknowledged per client (log lines = completed transactions)
    raw = rp.exec_in_client("sh", "-c", f"cat {prefix}* ; rm -f {prefix}*")
    acked = {}
    for line in raw.splitlines():
        parts = line.split()
        if parts:
            acked[int(parts[0])] = acked.get(int(parts[0]), 0) + 1
    present = {}
    for line in rp.psql("SELECT client_id, count(*) FROM rpo_events WHERE client_id >= 0 "
                        "GROUP BY 1").splitlines():
        c, n = line.split("|")
        present[int(c)] = int(n)
    lost = sum(max(0, acked.get(c, 0) - present.get(c, 0)) for c in acked)
    extra = sum(max(0, present.get(c, 0) - acked.get(c, 0)) for c in present)
    recloned = 0
    try:
        wait_healthy(CFG["rejoin_wait_s"])          # does the old primary rejoin by itself?
        t_full = time.time() - t_kill
    except RuntimeError:
        print("    old primary did not rejoin: re-cloning it", flush=True)
        reclone(old_primary)
        recloned = 1
        wait_healthy(CFG["healthy_timeout_s"])
        t_full = float("nan")
    return dict(killed_pod=old_primary, acked=sum(acked.values()), present=sum(present.values()),
                lost=lost, extra=extra,
                t_promote_s=round(t_promote, 1) if t_promote is not None else "",
                t_write_s=round(t_write, 1) if t_write is not None else "",
                t_full_s=round(t_full, 1) if t_full == t_full else "", recloned=recloned)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="1 repetition per level")
    ap.add_argument("--scenarios", nargs="+", choices=["CRASH", "ISOLATE"], default=None)
    ap.add_argument("--isolate-s", type=float, default=None)
    ap.add_argument("--levels", nargs="+", choices=list(LEVELS), default=None)
    ap.add_argument("--reps", type=int, default=None)
    ap.add_argument("--rate", type=int, nargs="+", default=None,
                    help="limit the total write rate of the 8 clients (pgbench -R, tps); several values allowed; "
                         "output defaults to results/rpo_rate.csv")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    if a.quick:
        CFG.update(reps=1, out=os.path.join("results", "rpo_quick.csv"))
    if a.scenarios:
        CFG["scenarios"] = a.scenarios
    if a.isolate_s is not None:
        CFG["isolate_s"] = a.isolate_s
    if a.reps is not None:
        CFG["reps"] = a.reps
    rates = a.rate or [None]
    if a.out:
        CFG["out"] = a.out
    elif a.rate:
        CFG["out"] = os.path.join("results", "rpo_rate.csv")
    fields = FIELDS + (["rate_tps"] if a.rate else [])
    levels = a.levels or list(LEVELS)
    os.makedirs("results", exist_ok=True)
    rp.PW = rp.get_password()
    if os.path.exists(CFG["out"]):                      # old CSV without 'scenario' column
        with open(CFG["out"], newline="") as fh:
            header = fh.readline()
        if "scenario" not in header:
            os.replace(CFG["out"], CFG["out"].replace(".csv", "_old.csv"))
    done = set()
    if os.path.exists(CFG["out"]):
        with open(CFG["out"], newline="") as fh:
            for r in csv.DictReader(fh):
                done.add((int(r["rep"]), r["level"], int(r["delay_ms"]), r["scenario"], round(float(r.get("isolate_s") or 0), 1), int(float(r.get("rate_tps") or 0))))
    new = not os.path.exists(CFG["out"])
    rng = random.Random(CFG["seed"])
    conds = [(l, d, sc, rt) for sc in CFG["scenarios"] for d in CFG["delays_ms"] for l in levels for rt in rates]
    with open(CFG["out"], "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        if new:
            w.writeheader()
        for rep in range(CFG["reps"]):
            order = conds[:]
            rng.shuffle(order)
            for i, (lvl, d, sc, rt) in enumerate(order):
                iso = round(CFG["isolate_s"], 1) if sc == "ISOLATE" else 0.0
                if (rep, lvl, d, sc, iso, rt or 0) in done:
                    continue
                print(f"[rep {rep+1}/{CFG['reps']}] run {i+1}/{len(order)}: {sc} / {lvl}, delay {d} ms" + (f", rate {rt} tps" if rt else ""), flush=True)
                res = one_run(rep, i, lvl, d, sc, rt)
                w.writerow(dict(rep=rep, order=i, scenario=sc, level=lvl, delay_ms=d,
                                isolate_s=CFG["isolate_s"] if sc == "ISOLATE" else 0,
                                timestamp=datetime.datetime.now().isoformat(timespec="seconds"),
                                **({"rate_tps": rt} if a.rate else {}), **res))
                fh.flush()
                print(f"    acked={res['acked']} lost={res['lost']} promote={res['t_promote_s']}s "
                      f"write_recovered={res['t_write_s']}s", flush=True)
    print("Done. Results in", CFG["out"])


if __name__ == "__main__":
    try:
        main()
    finally:
        try:
            rp.set_delay(0)
        except Exception:
            pass
