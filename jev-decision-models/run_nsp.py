"""The rostering study: every method on 20 small (10 nurses x 7 days) and 20 medium (25 nurses x 28 days) instances.

    python3 run_nsp.py                  # calls the models (answers are cached in cache/)
    DECIDE_REPLAY=1 python3 run_nsp.py  # replays the cached answers, no key needed
    python3 run_nsp.py --no-kev

Writes results/nsp.json (every run) and results/nsp_rosters.json (every roster, for the slides).
"""
import argparse
import json
import os
import statistics as S
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

import nsp
from decide import Decider

SEEDS = range(20)
REPS = 3
SAMPLES = 8
CPSAT_SECONDS = {"small": 10, "medium": 60}
ANNEAL = {"small": 50000, "medium": 500000}     # the classic heuristic: greedy, then a long annealing run
POLISH = {"small": 5000, "medium": 50000}       # a short polish, the same for every starting roster
GATE = 0.6                                      # the shortlist hybrid trusts the model only at or above this probability


def model_run(decider, inst, mode, version, rep, sample=False):
    tag = "full/%s/v%d/%s%d" % (mode, version, "sample" if sample else "rep", rep)
    if mode.startswith("top3"):          # greedy's 3 best nurses per place; "top3gate": the rule decides below p 0.6
        tag = "full/top3/v%d/rep%d" % (version, rep)      # one tag for both: they share calls until they differ
        pol = nsp.shortlist_policy(decider, tag=tag, version=version, gate=GATE if mode == "top3gate" else None)
    else:
        pol = nsp.model_policy(decider, mode=mode, tag=tag, version=version, sample=sample)
    t = time.time()
    R = nsp.rollout(inst, pol)
    return {"penalty": nsp.penalty(inst, R), "roster": R, "sec": sum(r["latency_ms"] or 0 for r in pol.log) / 1000, "calls": len(pol.log),
            "cost": sum((r["usage"] or {}).get("cost", 0) for r in pol.log),
            "latency_ms": S.median([r["latency_ms"] for r in pol.log if r["latency_ms"]] or [0]),
            "greedy_agree": S.mean(r["greedy_agree"] if "greedy_agree" in r else r["pick"] == r["rule"] for r in pol.log),
            "model_used": S.mean(r.get("used_model", True) for r in pol.log)}


def cpu_job(args):
    kind, inst, arg = args
    t = time.time()
    if kind == "cpsat":
        R, status, bound = nsp.cpsat(inst, arg)
        return {"penalty": nsp.penalty(inst, R), "roster": R, "sec": time.time() - t, "status": status, "bound": bound}
    roster, iters = arg
    R = nsp.anneal(inst, roster, iters=iters)
    return {"penalty": nsp.penalty(inst, R), "roster": R, "sec": time.time() - t}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-kev", action="store_true")
    ap.add_argument("--kev-only", action="store_true", help="only run the open model (fills its cache), then stop")
    ap.add_argument("--only", choices=["small", "medium"])
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    jev = Decider("jev", study="nsp")
    kev = None if a.no_kev else Decider("kev", study="nsp")
    sizes = [a.only] if a.only else ["small", "medium"]
    insts = {sz: [nsp.make_instance(sz, seed) for seed in SEEDS] for sz in sizes}
    res = {}
    for sz in sizes:
        for inst in insts[sz]:
            t = time.time()
            R = nsp.rollout(inst, nsp.greedy)
            res[inst["name"]] = {"size": sz, "greedy": {"penalty": nsp.penalty(inst, R), "roster": R, "sec": time.time() - t}}

    jobs, kjobs = [], []
    for sz in sizes:
        for inst in insts[sz]:
            for rep in range(REPS):
                jobs.append((inst, "jev_score_v1", jev, "score", 1, rep, False))
                jobs.append((inst, "jev_score_v2", jev, "score", 2, rep, False))
                jobs.append((inst, "jev_choice_v2", jev, "choice", 2, rep, False))
                jobs.append((inst, "jev_top3_v2", jev, "top3", 2, rep, False))
                jobs.append((inst, "jev_top3gate_v2", jev, "top3gate", 2, rep, False))
            for rep in range(SAMPLES):
                jobs.append((inst, "jev_sample8_v2", jev, "choice", 2, rep, True))
            if kev:
                kjobs.append((inst, "kev_score_v2", kev, "score", 2, 0, False))
                kjobs.append((inst, "kev_choice_v2", kev, "choice", 2, 0, False))

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
    for r in res.values():
        for method, v in list(r.items()):
            if isinstance(v, dict) and "runs" in v:
                runs = v["runs"]
                sample = method.startswith("jev_sample")
                best = min(runs, key=lambda x: x["penalty"][0])
                v["penalty"] = best["penalty"] if sample else [S.mean(x["penalty"][j] for x in runs) for j in range(4)]
                v["roster"] = best["roster"] if sample else runs[0]["roster"]
                div = 1 if sample else len(runs)
                v["sec"] = sum(x["sec"] for x in runs) / div
                v["calls"] = sum(x["calls"] for x in runs) / div
                v["cost"] = sum(x["cost"] for x in runs) / div
                v["latency_ms"] = S.median(x["latency_ms"] for x in runs)
                v["greedy_agree"] = S.mean(x["greedy_agree"] for x in runs)
                v["model_used"] = S.mean(x["model_used"] for x in runs)

    # CP-SAT, the long annealing run from greedy, and a short polish from every method's roster
    starts = ["greedy", "jev_score_v2", "jev_choice_v2", "jev_sample8_v2", "jev_top3_v2", "jev_top3gate_v2", "kev_score_v2", "kev_choice_v2"]
    cjobs = []
    for sz in sizes:
        for inst in insts[sz]:
            r = res[inst["name"]]
            cjobs.append((inst["name"], "cpsat", ("cpsat", inst, CPSAT_SECONDS[sz])))
            cjobs.append((inst["name"], "greedy+anneal", ("anneal", inst, (r["greedy"]["roster"], ANNEAL[sz]))))
            for st in starts:
                if st in r:
                    cjobs.append((inst["name"], st + "+polish", ("anneal", inst, (r[st]["roster"], POLISH[sz]))))
    print("  CPU jobs:", len(cjobs), flush=True)
    with ProcessPoolExecutor(4) as px:
        for (nm, method, _), out in zip(cjobs, px.map(cpu_job, [j[2] for j in cjobs])):
            res[nm][method] = out

    for r in res.values():
        best = min(v["penalty"][0] for v in r.values() if isinstance(v, dict) and "penalty" in v)
        r["best"] = best
        for v in r.values():
            if isinstance(v, dict) and "penalty" in v:
                v["over_best"] = v["penalty"][0] - best
                v["gap"] = (v["penalty"][0] / best - 1) * 100 if best else 0.0
    os.makedirs("results", exist_ok=True)
    rosters = {nm: {m: v["roster"] for m, v in r.items() if isinstance(v, dict) and "roster" in v} for nm, r in res.items()}
    for r in res.values():
        for v in r.values():
            if isinstance(v, dict):
                v.pop("roster", None)
                for x in v.get("runs", []):
                    x.pop("roster", None)
    json.dump({"results": res}, open("results/nsp.json", "w"), indent=1)
    json.dump(rosters, open("results/nsp_rosters.json", "w"))
    for sz in sizes:
        rows = [r for r in res.values() if r["size"] == sz]
        opt = sum(r["cpsat"]["status"] == "OPTIMAL" for r in rows)
        print("\n%s (%d instances, CP-SAT optimal on %d)   penalty over best: mean ± std (gap %%) | time | calls | cost/instance" % (sz, len(rows), opt))
        methods = [m for m in rows[0] if isinstance(rows[0][m], dict) and "gap" in rows[0][m]]
        for m in sorted(methods, key=lambda m: S.mean(r[m]["over_best"] for r in rows)):
            o = [r[m]["over_best"] for r in rows]
            print("  %-24s +%6.1f ± %5.1f (%5.1f%%) | %6.2fs | %5.1f | $%.5f" % (
                m, S.mean(o), S.pstdev(o), S.mean(r[m]["gap"] for r in rows), S.mean(r[m]["sec"] for r in rows),
                S.mean(r[m].get("calls", 0) for r in rows), S.mean(r[m].get("cost", 0) for r in rows)))
    print("new API calls: jev %d (cached %d)%s" % (jev.calls, jev.hits, "; kev %d" % kev.calls if kev else ""))


if __name__ == "__main__":
    main()
