"""Write every number the slides show into ../assets/data.js, straight from the frozen results and the cache.

    python3 export_slides.py                 # → ../assets/data.js, which the deck reads
    python3 export_slides.py slide_data.js   # or any other path

The slides never hand-copy a number: scenes read window.DATA, and the narration quotes what this prints.
Inputs: results/runs/2026-10-30c-final/, results/examples/, cache/*.jsonl (or the shipped .jsonl.gz).
"""
import gzip
import json
import math
import os
import statistics as S
import sys

import cvrp
import nsp

HERE = os.path.dirname(os.path.abspath(__file__))
RUN = os.path.join(HERE, "results/runs/2026-10-30c-final")
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "../assets/data.js")


def load(name):
    return json.load(open(os.path.join(RUN, name)))


def cache_lines(name):
    p = os.path.join(HERE, "cache", name)
    return open(p) if os.path.exists(p) else gzip.open(p + ".gz", "rt")


def means(rows, methods, key):
    return {m: round(S.mean(r[m][key] for r in rows), 1) for m in methods if m in rows[0]}


def mean_cost(rows, m):
    return round(S.mean(r[m].get("cost", 0) for r in rows), 5)


def paired(rows, a, b):
    d = [r[a]["gap"] - r[b]["gap"] for r in rows]
    m, se = S.mean(d), S.stdev(d) / math.sqrt(len(d))
    return {"diff": round(m, 2), "lo": round(m - 1.96 * se, 2), "hi": round(m + 1.96 * se, 2),
            "wins": sum(x < 0 for x in d), "losses": sum(x > 0 for x in d)}


def calib_bins(rows):
    out = []
    for lo in (0.2, 0.4, 0.6, 0.8):
        b = [r for r in rows if lo <= r["p"] < lo + 0.2 or (lo == 0.8 and r["p"] == 1.0)]
        out.append({"lo": lo, "hi": round(lo + 0.2, 1), "n": len(b), "right": round(100 * S.mean(r["right"] for r in b), 1),
                    "mean_p": round(S.mean(r["p"] for r in b), 3)})
    return out


def cache_stats():
    calls, cost, lat, by_opts = 0, 0.0, [], {}
    for name in ("jev.jsonl", "jev-nsp.jsonl", "jev-notes.jsonl"):
        for line in cache_lines(name):
            r = json.loads(line)
            calls += 1
            cost += (r.get("usage") or {}).get("cost", 0) or 0
            if r.get("latency_ms"):
                lat.append(r["latency_ms"])
            for a in r["answers"].values():
                if a.get("type") == "choice" and len(r["answers"]) == 1 and r.get("latency_ms"):
                    by_opts.setdefault(len(a["probabilities"]), []).append(r["latency_ms"])
    buckets = [(2, 3), (4, 6), (7, 10), (11, 16), (17, 25), (26, 51)]
    lat_opts = []
    for lo, hi in buckets:
        v = [x for k, xs in by_opts.items() if lo <= k <= hi for x in xs]
        if v:
            lat_opts.append({"opts": "%d–%d" % (lo, hi), "median_ms": round(S.median(v)), "n": len(v)})
    kev = sum(1 for n in ("kev.jsonl", "kev-nsp.jsonl", "kev-notes.jsonl") for _ in cache_lines(n))
    return {"jev_calls": calls, "kev_calls": kev, "jev_cost": round(cost, 2), "median_ms": round(S.median(lat)),
            "cost_per_call": round(cost / calls, 6), "latency_by_options": lat_opts}


def main():
    D = {"totals": cache_stats()}

    # ── routing ──
    cv = load("cvrp.json")
    R = cv["results"]
    methods = ["ortools_ref", "ortools_1s", "clarke_wright", "nearest", "jev_choice_v1", "jev_choice_v2", "jev_score_v2",
               "jev_sample8_v2", "jev_top3_v2", "jev_top3gate_v2", "kev_choice_v2", "kev_score_v2",
               "clarke_wright+ortools_1s", "jev_sample8_v2+ortools_1s", "nearest+ortools_1s", "jev_choice_v2+ortools_1s"]
    C = {}
    for sz in ("small", "medium"):
        rows = [r for r in R.values() if r["size"] == sz]
        C[sz] = {"gap": means(rows, methods, "gap"),
                 "cost": {m: mean_cost(rows, m) for m in methods if m.startswith(("jev", "kev")) and "+" not in m},
                 "calib": calib_bins([c for c in cv["calibration"] if c["size"] == sz]),
                 "calib_n": sum(1 for c in cv["calibration"] if c["size"] == sz),
                 "calib_right": round(100 * S.mean(c["right"] for c in cv["calibration"] if c["size"] == sz), 1)}
    med = [r for r in R.values() if r["size"] == "medium"]
    C["medium"]["paired"] = {"jev8_vs_cw": paired(med, "jev_sample8_v2+ortools_1s", "clarke_wright+ortools_1s"),
                             "jev8_vs_cold": paired(med, "jev_sample8_v2+ortools_1s", "ortools_1s"),
                             "cw_vs_cold": paired(med, "clarke_wright+ortools_1s", "ortools_1s")}
    routes = load("cvrp_routes.json")

    # the first decision of the first map: small seed 0, the real board and answer
    ex = json.load(open(os.path.join(HERE, "results/examples/cvrp_small_jev_choice_v2.json")))
    probs = ex["answers"]["next"]["probabilities"]
    inst = cvrp.make_instance(10, 0)
    D["first_call"] = {"xy": inst["xy"], "demand": inst["demand"], "Q": inst["Q"], "probs": probs,
                       "confidence": ex["answers"]["next"]["confidence"], "board": ex["state"],
                       "question": ex["questions"]["next"]["instructions"], "latency_ms": ex["latency_ms"]}
    sc = json.load(open(os.path.join(HERE, "results/examples/cvrp_small_jev_score_v2.json")))
    D["first_score"] = {"stop": "S1", **{k: sc["answers"]["S1"][k] for k in ("score", "probabilities", "legend")}}

    # Clarke & Wright: the biggest saving on the same map
    best = max(((cvrp.dist(inst, 0, i) + cvrp.dist(inst, 0, j) - cvrp.dist(inst, i, j), i, j)
                for i in range(1, 11) for j in range(i + 1, 11)))
    sv, i, j = best
    D["cw_example"] = {"i": i, "j": j, "d0i": round(cvrp.dist(inst, 0, i), 1), "d0j": round(cvrp.dist(inst, 0, j), 1),
                       "dij": round(cvrp.dist(inst, i, j), 1), "saving": round(sv, 1)}
    D["small_map"] = {"name": "cvrp10-s0", "routes": {m: routes["cvrp10-s0"][m] for m in ("nearest", "clarke_wright", "jev_choice_v1", "ortools_ref")},
                      "length": {m: round(R["cvrp10-s0"][m]["length"], 1) for m in ("nearest", "clarke_wright", "jev_choice_v1", "ortools_ref")}}

    # a typical 50-stop map for the side-by-side: the instance whose Jev gap is closest to Jev's mean gap
    target = C["medium"]["gap"]["jev_choice_v1"]
    nm = min((r for r in R if R[r]["size"] == "medium"), key=lambda n: abs(R[n]["jev_choice_v1"]["gap"] - target))
    mi = cvrp.make_instance(50, int(nm.split("-s")[1]))
    D["medium_map"] = {"name": nm, "xy": mi["xy"], "routes": {m: routes[nm][m] for m in ("jev_choice_v1", "clarke_wright", "ortools_ref")},
                       "gap": {m: round(R[nm][m]["gap"], 1) for m in ("jev_choice_v1", "clarke_wright", "ortools_ref")}}
    D["cvrp"] = C

    # ── rostering ──
    ns = load("nsp.json")["results"]
    nmethods = ["cpsat", "greedy", "greedy+anneal", "greedy+polish", "jev_score_v1", "jev_score_v2", "jev_choice_v2",
                "jev_sample8_v2", "jev_top3_v2", "jev_top3gate_v2", "kev_score_v2", "kev_choice_v2", "jev_top3gate_v2+polish"]
    N = {}
    for sz in ("small", "medium"):
        rows = [r for r in ns.values() if r["size"] == sz]
        N[sz] = {"over": means(rows, nmethods, "over_best"),
                 "cost": {m: mean_cost(rows, m) for m in nmethods if m.startswith(("jev", "kev")) and "+" not in m},
                 "cpsat_optimal": sum(r["cpsat"]["status"] == "OPTIMAL" for r in rows),
                 "cpsat_sec": round(S.mean(r["cpsat"]["sec"] for r in rows), 2),
                 "top3_kept": {m: round(100 * S.mean(r[m]["model_used"] for r in rows)) for m in ("jev_top3_v2", "jev_top3gate_v2")},
                 "top3_beats_rule": {m: sum(r[m]["over_best"] < r["greedy"]["over_best"] for r in rows) for m in ("jev_top3_v2", "jev_top3gate_v2")}}
    for sz in ("small", "medium"):
        rows = [r for r in R.values() if r["size"] == sz]
        C[sz]["top3_kept"] = {m: round(100 * S.mean(r[m]["model_used"] for r in rows)) for m in ("jev_top3_v2", "jev_top3gate_v2")}
        C[sz]["top3_same_as_rule"] = {m: round(100 * S.mean(r[m]["same_as_nearest"] for r in rows)) for m in ("jev_top3_v2", "jev_top3gate_v2")}
        C[sz]["top3_beats_rule"] = {m: sum(r[m]["gap"] < r["nearest"]["gap"] for r in rows) for m in ("jev_top3_v2", "jev_top3gate_v2")}
    rost = load("nsp_rosters.json")["nsp-small-s0"]
    si = nsp.make_instance("small", 0)
    N["small_s0"] = {"N": si["N"], "D": si["D"], "cover": si["cover"], "off": si["off"], "avoid": si["avoid"],
                     "rosters": {m: rost[m] for m in ("greedy", "jev_score_v2", "cpsat")},
                     "penalty": {m: nsp.penalty(si, rost[m]) for m in ("greedy", "jev_score_v2", "cpsat")}}
    N["weights"] = {"request": nsp.REQUEST, "avoid": nsp.AVOID, "fair": nsp.FAIR}
    D["nsp"] = N
    big = nsp.make_instance("medium", 0)
    D["scale"] = {"cvrp_maps": len(R), "cvrp_stops_max": len(cvrp.make_instance(50, 0)["xy"]) - 1,
                  "nsp_rosters": len(ns), "nsp_nurses_max": big["N"], "nsp_days_max": big["D"]}

    # ── notes ──
    nj, nk = load("notes_jev.json"), load("notes_kev.json")
    D["notes"] = {"jev": nj["summary"], "kev": nk["summary"],
                  "rows": [{k: x[k] for k in ("note", "true_off", "true_avoid", "read_off", "read_avoid", "all_right", "unsure", "p_days", "p_avoid")}
                           for x in nj["notes"]]}
    ex = json.load(open(os.path.join(HERE, "results/examples/notes_jev.json")))
    D["notes"]["questions"] = ex["questions"]
    D["scale"]["notes"] = len(nj["notes"])

    os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
    with open(OUT, "w") as f:
        f.write("/* Generated by code/export_slides.py from code/results/runs/2026-10-30c-final. Do not edit by hand. */\n")
        f.write("window.DATA = " + json.dumps(D, ensure_ascii=False, separators=(",", ":")) + ";\n")
    t = D["totals"]
    print("wrote", OUT, "(%.0f kB)" % (os.path.getsize(OUT) / 1000))
    print("totals:", t)
    print("first call:", D["first_call"]["probs"], D["first_call"]["confidence"], "| score:", D["first_score"])
    print("cw example:", D["cw_example"], "| medium map:", nm, D["medium_map"]["gap"])
    print("small map lengths:", D["small_map"]["length"])
    print("roster s0:", N["small_s0"]["penalty"])
    print("routing paired:", C["medium"]["paired"])
    print("scale:", D["scale"])
    print("latency by options:", t["latency_by_options"])


if __name__ == "__main__":
    main()
