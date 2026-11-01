"""The routing study: every method on 20 small (10 stops) and 20 medium (50 stops) instances.

    python3 run_cvrp.py                 # calls the models (answers are cached in cache/)
    DECIDE_REPLAY=1 python3 run_cvrp.py # replays the cached answers, no key needed
    python3 run_cvrp.py --no-kev        # skip the local open model

Writes results/cvrp.json (every run) and results/cvrp_routes.json (every route, for the slides).
OR-Tools times are wall-clock limits, so its numbers can move a little from machine to machine.
"""
import argparse
import json
import os
import statistics as S
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

import cvrp
from decide import Decider

SIZES = {"small": 10, "medium": 50}
SEEDS = range(20)
REPS = 3
SAMPLES = 8
REF_SECONDS = {"small": 10, "medium": 60}
SHORT = 300                 # "ortools_1s": a fixed 300-solution budget, about 1 s on an idle M4 Pro, and repeatable
REF_FILE = "results/reference_routes.json"   # the long OR-Tools runs, frozen: the calibration probe walks these routes
GATE = 0.6                  # the shortlist hybrid trusts the model only at or above this probability


def model_run(decider, inst, mode, version, rep, sample=False):
    tag = "full/%s/v%d/%s%d" % (mode, version, "sample" if sample else "rep", rep)
    if mode.startswith("top3"):          # the rule's 3 nearest stops (+ depot); "top3gate": the rule decides below p 0.6
        tag = "full/top3/v%d/rep%d" % (version, rep)      # one tag for both: they share calls until they differ
        pol = cvrp.shortlist_policy(decider, tag=tag, version=version, gate=GATE if mode == "top3gate" else None)
    else:
        pol = cvrp.model_policy(decider, mode=mode, tag=tag, sample=sample, version=version)
    t = time.time()
    trips = cvrp.rollout(inst, pol)
    calls = [r for r in pol.log]
    return {"length": cvrp.length(inst, trips), "trips": trips, "sec": sum(r["latency_ms"] or 0 for r in calls) / 1000, "calls": len(calls),
            "cost": sum((r["usage"] or {}).get("cost", 0) for r in calls),
            "latency_ms": S.median([r["latency_ms"] for r in calls if r["latency_ms"]] or [0]),
            "same_as_nearest": sum(r["pick"] == r["nearest"] for r in calls) / max(1, len(calls)),
            "model_used": sum(r.get("used_model", True) for r in calls) / max(1, len(calls))}


def ortools_job(args):
    inst, seconds, initial = args
    t = time.time()
    trips = cvrp.ortools(inst, seconds, initial=initial, solutions=SHORT if seconds == 1 else None)
    return {"length": cvrp.length(inst, trips), "trips": trips, "sec": time.time() - t}


def calibration_probe(decider, inst, ref_trips):
    """Walk the reference route and ask the model for the next move at every state.
    'Right' = a move the reference makes: from the depot, either end of any trip still to do."""
    out, s, todo, cur = [], cvrp.start(inst), [list(t) for t in ref_trips], None
    while todo or cur or s["at"] != 0:
        opts = cvrp.legal(inst, s)
        right = ({t[0] for t in todo} | {t[-1] for t in todo}) if cur is None else ({cur[0]} if cur else {0})
        if len(opts) > 1:
            pol = cvrp.model_policy(decider, mode="choice", tag="calib/v2", version=2)
            pick = pol(inst, s)
            r = pol.log[-1]
            out.append({"p": r["p"], "conf": r["conf"], "right": pick in right, "n_opts": r["n_opts"]})
        if cur is None:                      # follow the reference, not the model
            t = todo.pop(0)
            nxt, cur = t[0], t[1:]
        elif cur:
            nxt = cur.pop(0)
        else:
            nxt, cur = 0, None
        s = cvrp.step(inst, s, nxt)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-kev", action="store_true")
    ap.add_argument("--kev-only", action="store_true", help="only run the open model (fills its cache), then stop")
    ap.add_argument("--only", choices=list(SIZES))
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    jev = Decider("jev")
    kev = None if a.no_kev else Decider("kev")
    sizes = [a.only] if a.only else list(SIZES)
    insts = {sz: [cvrp.make_instance(SIZES[sz], seed) for seed in SEEDS] for sz in sizes}
    res = {}

    # 1 · instant baselines
    for sz in sizes:
        for inst in insts[sz]:
            r = res.setdefault(inst["name"], {"size": sz})
            for name, f in [("nearest", lambda: cvrp.rollout(inst, cvrp.nearest)), ("clarke_wright", lambda: cvrp.clarke_wright(inst))]:
                t = time.time()
                trips = f()
                r[name] = {"length": cvrp.length(inst, trips), "trips": trips, "sec": time.time() - t}

    # 2 · decision-model rollouts (threads: the time is spent waiting on the network)
    jobs = []
    for sz in sizes:
        for inst in insts[sz]:
            for rep in range(REPS):
                jobs.append((inst, "jev_choice_v1", jev, "choice", 1, rep, False))
                jobs.append((inst, "jev_choice_v2", jev, "choice", 2, rep, False))
                jobs.append((inst, "jev_score_v2", jev, "score", 2, rep, False))
                jobs.append((inst, "jev_top3_v2", jev, "top3", 2, rep, False))
                jobs.append((inst, "jev_top3gate_v2", jev, "top3gate", 2, rep, False))
            for rep in range(SAMPLES):
                jobs.append((inst, "jev_sample8_v2", jev, "choice", 2, rep, True))
    kjobs = []
    if kev:
        for sz in sizes:
            for inst in insts[sz]:
                kjobs.append((inst, "kev_choice_v2", kev, "choice", 2, 0, False))
                kjobs.append((inst, "kev_score_v2", kev, "score", 2, 0, False))

    if a.kev_only:
        jobs = []
    def go(job):
        inst, name, dec, mode, ver, rep, sample = job
        return inst["name"], name, model_run(dec, inst, mode, ver, rep, sample)

    t0 = time.time()
    with ThreadPoolExecutor(a.workers) as ex, ThreadPoolExecutor(1) as kx:
        futs = [ex.submit(go, j) for j in jobs] + [kx.submit(go, j) for j in kjobs]
        for i, f in enumerate(futs):
            nm, method, run = f.result()
            res[nm].setdefault(method, {"runs": []})["runs"].append(run)
            if (i + 1) % 50 == 0 or i + 1 == len(futs):
                print("  model runs %d/%d  %.0fs  (new calls: jev %d%s)" % (i + 1, len(futs), time.time() - t0, jev.calls,
                                                                         ", kev %d" % kev.calls if kev else ""), flush=True)
    if a.kev_only:
        print("kev runs done; new kev calls:", kev.calls)
        return
    for nm, r in res.items():
        for method, v in list(r.items()):
            if isinstance(v, dict) and "runs" in v:
                runs = v["runs"]
                if method.startswith("jev_sample"):
                    best = min(runs, key=lambda x: x["length"])
                    v.update({k: best[k] for k in ("length", "trips")})
                    v["sec"] = sum(x["sec"] for x in runs)
                else:
                    v["length"] = S.mean(x["length"] for x in runs)
                    v["trips"] = runs[0]["trips"]
                    v["sec"] = S.mean(x["sec"] for x in runs)
                v["calls"] = sum(x["calls"] for x in runs) / (1 if method.startswith("jev_sample") else len(runs))
                v["cost"] = sum(x["cost"] for x in runs) / (1 if method.startswith("jev_sample") else len(runs))
                v["latency_ms"] = S.median(x["latency_ms"] for x in runs)
                v["model_used"] = S.mean(x["model_used"] for x in runs)
                v["same_as_nearest"] = S.mean(x["same_as_nearest"] for x in runs)

    # 3 · OR-Tools: from scratch, the long reference run, and 1 s polishing every method's route
    warm = ["nearest", "clarke_wright", "jev_choice_v2", "jev_score_v2", "jev_sample8_v2", "jev_top3_v2", "jev_top3gate_v2", "kev_choice_v2", "kev_score_v2"]
    ojobs = []
    frozen = json.load(open(REF_FILE)) if os.path.exists(REF_FILE) else {}
    for sz in sizes:
        for inst in insts[sz]:
            r = res[inst["name"]]
            ojobs.append((inst["name"], "ortools_1s", (inst, 1, None)))
            if inst["name"] in frozen:           # OR-Tools stops on a wall clock, so a re-run can find another route
                r["ortools_ref"] = {k: frozen[inst["name"]][k] for k in ("length", "trips", "sec")}
            else:
                ojobs.append((inst["name"], "ortools_ref", (inst, REF_SECONDS[sz], None)))
            for w in warm:
                if w in r:
                    ojobs.append((inst["name"], w + "+ortools_1s", (inst, 1, r[w]["trips"])))
    print("  OR-Tools jobs:", len(ojobs), flush=True)
    with ProcessPoolExecutor(4) as px:
        for (nm, method, _), out in zip(ojobs, px.map(ortools_job, [j[2] for j in ojobs])):
            res[nm][method] = out

    # 4 · calibration: is the model's confidence honest on this task?
    calib = []
    with ThreadPoolExecutor(a.workers) as ex:
        futs = [ex.submit(calibration_probe, jev, inst, res[inst["name"]]["ortools_ref"]["trips"]) for sz in sizes for inst in insts[sz]]
        for sz_inst, f in zip([(sz, inst) for sz in sizes for inst in insts[sz]], futs):
            for row in f.result():
                calib.append({"size": sz_inst[0], **row})

    # gaps vs the best route any method found
    for nm, r in res.items():
        best = min(v["length"] for v in r.values() if isinstance(v, dict) and "length" in v)
        r["best"] = best
        for v in r.values():
            if isinstance(v, dict) and "length" in v:
                v["gap"] = (v["length"] / best - 1) * 100
    os.makedirs("results", exist_ok=True)
    if not frozen:
        json.dump({nm: {**{k: r["ortools_ref"][k] for k in ("length", "trips", "sec")}} for nm, r in res.items()}, open(REF_FILE, "w"), indent=1)
    routes = {nm: {m: v["trips"] for m, v in r.items() if isinstance(v, dict) and "trips" in v} for nm, r in res.items()}
    for r in res.values():
        for v in r.values():
            if isinstance(v, dict):
                v.pop("trips", None)
                for x in v.get("runs", []):
                    x.pop("trips", None)
    json.dump({"results": res, "calibration": calib}, open("results/cvrp.json", "w"), indent=1)
    json.dump(routes, open("results/cvrp_routes.json", "w"))
    summary(res, calib, sizes)
    print("new API calls: jev %d (cached %d)%s" % (jev.calls, jev.hits, "; kev %d" % kev.calls if kev else ""))


def summary(res, calib, sizes):
    for sz in sizes:
        rows = [r for r in res.values() if r["size"] == sz]
        methods = [m for m in rows[0] if isinstance(rows[0][m], dict) and "gap" in rows[0][m]]
        print("\n%s (%d instances)   gap vs best found: mean ± std | time | calls | cost/instance" % (sz, len(rows)))
        for m in sorted(methods, key=lambda m: S.mean(r[m]["gap"] for r in rows)):
            g = [r[m]["gap"] for r in rows]
            print("  %-28s %6.1f%% ± %5.1f | %6.2fs | %5.1f | $%.5f" % (
                m, S.mean(g), S.pstdev(g), S.mean(r[m]["sec"] for r in rows),
                S.mean(r[m].get("calls", 0) for r in rows), S.mean(r[m].get("cost", 0) for r in rows)))
        c = [x for x in calib if x["size"] == sz]
        if c:
            print("  calibration: %d states, picked the reference move %.0f%% of the time, mean confidence p %.2f" % (
                len(c), 100 * S.mean(x["right"] for x in c), S.mean(x["p"] for x in c)))
            for lo in (0, .2, .4, .6, .8):
                b = [x for x in c if lo <= x["p"] < lo + .2 or (lo == .8 and x["p"] == 1)]
                if b:
                    print("    p in [%.1f, %.1f): %4d states, right %.0f%%" % (lo, lo + .2, len(b), 100 * S.mean(x["right"] for x in b)))


if __name__ == "__main__":
    main()
