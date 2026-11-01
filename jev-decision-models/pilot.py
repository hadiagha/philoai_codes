"""Stage-3 pilot: one instance of each problem, every method, with timing and cost.

    python3 pilot.py            # calls Jev (cached afterwards)
    DECIDE_REPLAY=1 python3 pilot.py
"""
import json
import statistics as S
import sys
import time

import cvrp
import nsp
from decide import Decider


def model_cost(log):
    calls = len(log)
    ms = [r["latency_ms"] for r in log if r["latency_ms"] is not None]
    tok = sum((r["usage"] or {}).get("input_tokens", 0) for r in log)
    cost = sum((r["usage"] or {}).get("cost", 0) for r in log)
    return {"calls": calls, "median_ms": S.median(ms) if ms else None, "input_tokens": tok, "cost_usd": round(cost, 6)}


def run_cvrp(jev, n, seed):
    inst = cvrp.make_instance(n, seed)
    out = {}
    for name, f in [("nearest", lambda: cvrp.rollout(inst, cvrp.nearest)),
                    ("clarke_wright", lambda: cvrp.clarke_wright(inst)),
                    ("ortools_1s", lambda: cvrp.ortools(inst, 1)),
                    ("ortools_30s", lambda: cvrp.ortools(inst, 30))]:
        t = time.time()
        trips = f()
        out[name] = {"length": round(cvrp.length(inst, trips), 1), "trips": len(trips), "sec": round(time.time() - t, 2)}
    for mode in ("choice", "score"):
        pol = cvrp.model_policy(jev, mode=mode, tag="pilot/%s/rep0" % mode)
        t = time.time()
        trips = cvrp.rollout(inst, pol)
        out["jev_" + mode] = {"length": round(cvrp.length(inst, trips), 1), "trips": len(trips), "sec": round(time.time() - t, 2),
                              **model_cost(pol.log),
                              "same_as_nearest": round(sum(r["pick"] == r["nearest"] for r in pol.log) / len(pol.log), 2),
                              "depot_returns": sum(r["pick"] == 0 for r in pol.log)}
        out["jev_" + mode + "+ortools_1s"] = {"length": round(cvrp.length(inst, cvrp.ortools(inst, 1, initial=trips)), 1)}
    best = min(v["length"] for v in out.values())
    for v in out.values():
        v["gap_%"] = round((v["length"] / best - 1) * 100, 1)
    return inst["name"], out


def run_nsp(jev, size, seed):
    inst = nsp.make_instance(size, seed)
    out = {}
    t = time.time()
    g = nsp.rollout(inst, nsp.greedy)
    out["greedy"] = {"penalty": nsp.penalty(inst, g), "sec": round(time.time() - t, 2)}
    t = time.time()
    out["greedy+anneal"] = {"penalty": nsp.penalty(inst, nsp.anneal(inst, g, iters=50000 if size == "small" else 300000)),
                            "sec": round(time.time() - t, 2)}
    t = time.time()
    R, status, bound = nsp.cpsat(inst, 10 if size == "small" else 30)
    out["cpsat"] = {"penalty": nsp.penalty(inst, R), "status": status, "sec": round(time.time() - t, 2)}
    for mode in ("score", "choice"):
        pol = nsp.model_policy(jev, mode=mode, tag="pilot/%s/rep0" % mode)
        t = time.time()
        R = nsp.rollout(inst, pol)
        out["jev_" + mode] = {"penalty": nsp.penalty(inst, R), "sec": round(time.time() - t, 2), **model_cost(pol.log),
                              "agree_with_greedy": round(S.mean(r["greedy_agree"] for r in pol.log), 2)}
    return inst["name"], out


if __name__ == "__main__":
    jev = Decider("jev")
    results = {}
    for args in [(10, 0), (50, 0)]:
        k, v = run_cvrp(jev, *args)
        results[k] = v
        print(k, json.dumps(v, indent=1))
    for args in [("small", 0), ("medium", 0)]:
        k, v = run_nsp(jev, *args)
        results[k] = v
        print(k, json.dumps(v, indent=1))
    print("new API calls:", jev.calls, "cached:", jev.hits)
    json.dump(results, open("results/pilot.json", "w"), indent=1)
