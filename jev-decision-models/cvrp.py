"""Capacitated vehicle routing (CVRP) as a Markov decision process, plus the methods we compare.

One van starts at the depot, delivers to every stop exactly once, and goes back to the depot to
reload whenever its load runs out. The goal is the shortest total distance over all trips.

    state  = where the van is, load left, stops left
    action = the next stop, or back to the depot
    mask   = code removes illegal moves (already visited, or doesn't fit the load left)
    reward = minus the distance driven

Instances follow Kool, van Hoof & Welling (ICLR 2019): uniform locations, demand 1-9, capacity
20 / 30 / 40 / 50 for 10 / 20 / 50 / 100 stops. Locations are on a 0-100 grid so the text is easy to read.
"""
import math
import random

CAPACITY = {10: 20, 20: 30, 50: 40, 100: 50}


def make_instance(n, seed):
    rng = random.Random("cvrp/%d/%d" % (n, seed))
    xy = [(50, 50)] + [(rng.randint(0, 100), rng.randint(0, 100)) for _ in range(n)]
    demand = [0] + [rng.randint(1, 9) for _ in range(n)]
    return {"name": "cvrp%d-s%d" % (n, seed), "n": n, "seed": seed, "xy": xy, "demand": demand, "Q": CAPACITY[n]}


def dist(inst, a, b):
    (x1, y1), (x2, y2) = inst["xy"][a], inst["xy"][b]
    return math.hypot(x1 - x2, y1 - y2)


def length(inst, trips):
    return sum(dist(inst, a, b) for t in trips for a, b in zip([0] + t, t + [0]))


def check(inst, trips):
    seen = sorted(c for t in trips for c in t)
    assert seen == list(range(1, inst["n"] + 1)), "every stop exactly once"
    assert all(sum(inst["demand"][c] for c in t) <= inst["Q"] for t in trips), "capacity"
    return True


# ── the MDP ─────────────────────────────────────────────────────────────

def start(inst):
    return {"at": 0, "load": inst["Q"], "left": set(range(1, inst["n"] + 1)), "trips": [[]], "steps": 0}


def legal(inst, s):
    fits = sorted(c for c in s["left"] if inst["demand"][c] <= s["load"])
    if s["at"] == 0:
        return fits                         # never depot → depot
    return fits + [0]                       # going back to reload is always allowed


def step(inst, s, a):
    s = {"at": a, "load": s["load"], "left": set(s["left"]), "trips": [list(t) for t in s["trips"]], "steps": s["steps"] + 1}
    if a == 0:
        s["load"] = inst["Q"]
        s["trips"].append([])
    else:
        s["left"].discard(a)
        s["load"] -= inst["demand"][a]
        s["trips"][-1].append(a)
    return s


def done(s):
    return not s["left"] and s["at"] == 0


def rollout(inst, policy):
    s = start(inst)
    while s["left"]:
        s = step(inst, s, policy(inst, s))
    if s["at"] != 0:
        s = step(inst, s, 0)
    trips = [t for t in s["trips"] if t]
    check(inst, trips)
    return trips


# ── the board as text (what the decision model reads) ───────────────────

def name(c):
    return "DEPOT" if c == 0 else "S%d" % c


def board(inst, s, options, version=1):
    at, Q = s["at"], inst["Q"]
    left_demand = sum(inst["demand"][c] for c in s["left"])
    lines = [
        "Delivery van route planning. Goal: deliver to every stop exactly once with the smallest total distance.",
        "The van carries at most %d units. It reloads only at the DEPOT at (50,50). Every trip starts and ends at the DEPOT." % Q,
        "Now: the van is at %s (%d,%d). Load left: %d of %d. Stops left: %d, total demand %d." % (
            name(at), *inst["xy"][at], s["load"], Q, len(s["left"]), left_demand),
        "Legal next moves:",
    ]
    if version >= 2:   # v2: the facts a dispatcher would check, worked out by code
        lines.insert(3, "Full loads still needed for the demand left: at least %d more trip%s after this one." % (
            max(0, -(-(left_demand - s["load"]) // Q)), "" if -(-(left_demand - s["load"]) // Q) == 1 else "s"))
    for c in options:
        if c == 0:
            extra = " Going back now leaves %d units unused on this trip." % s["load"] if version >= 2 else ""
            lines.append("DEPOT at (50,50): %.1f away. Reload to %d.%s" % (dist(inst, at, 0), Q, extra))
        else:
            extra = ""
            if version >= 2:
                near = sorted(dist(inst, c, o) for o in s["left"] if o != c)[:3]
                extra = " Load left after it: %d. Its 3 nearest other stops left: %s." % (
                    s["load"] - inst["demand"][c], ", ".join("%.1f" % x for x in near) or "none")
            lines.append("%s at (%d,%d): demand %d, %.1f away, %.1f from the depot.%s" % (
                name(c), *inst["xy"][c], inst["demand"][c], dist(inst, at, c), dist(inst, c, 0), extra))
    blocked = sorted(c for c in s["left"] if inst["demand"][c] > s["load"])
    if blocked:
        lines.append("Stops left that need a reload first: " + ", ".join(
            "%s at (%d,%d) demand %d" % (name(c), *inst["xy"][c], inst["demand"][c]) for c in blocked) + ".")
    return "\n".join(lines)


# ── policies ────────────────────────────────────────────────────────────

def nearest(inst, s):
    opts = [c for c in legal(inst, s) if c != 0]
    return min(opts, key=lambda c: dist(inst, s["at"], c)) if opts else 0


LEVELS = ["Very bad", "Bad", "Okay", "Good", "Very good"]


def model_policy(decider, mode="choice", tag="", sample=False, version=1):
    """Use a decision model as the policy. mode 'choice' = one question over all legal moves;
    mode 'score' = one score question per legal move, all in the same call."""
    log = []

    def policy(inst, s):
        opts = legal(inst, s)
        if len(opts) == 1:
            return opts[0]
        rng = random.Random("%s/%s/%d" % (inst["name"], tag, s["steps"]))
        opts = rng.sample(opts, len(opts))          # shuffle: the model leans towards the first option
        state = board(inst, s, opts, version)
        if mode == "choice":
            q = {"next": {"type": "choice",
                          "instructions": "Which move should the van make next so that the total distance of all trips is as small as possible?",
                          "criteria": {name(c): ("go back to the DEPOT and reload" if c == 0 else "go to " + name(c)) for c in opts}}}
            ans, rec = decider.ask(state, q, tag="%s/%s/%d" % (inst["name"], tag, s["steps"]))
            p = {c: ans["next"]["probabilities"].get(name(c), 0.0) for c in opts}
            conf = ans["next"].get("confidence")
        else:
            q = {name(c): {"type": "score",
                           "instructions": ("How good is it to go back to the DEPOT and reload now" if c == 0 else "How good is it to go to %s next" % name(c))
                                           + ", for the smallest total distance of all trips?",
                           "criteria": LEVELS} for c in opts}
            ans, rec = decider.ask(state, q, tag="%s/%s/%d" % (inst["name"], tag, s["steps"]))
            p = {c: ans[name(c)]["score"] for c in opts}
            conf = None
        if sample and mode == "choice":
            tot = sum(p.values()) or 1.0
            r, acc, pick = rng.random() * tot, 0.0, opts[-1]
            for c in opts:
                acc += p[c]
                if r <= acc:
                    pick = c
                    break
        else:
            pick = max(opts, key=lambda c: (p[c], -dist(inst, s["at"], c)))
        log.append({"step": s["steps"], "n_opts": len(opts), "pick": pick, "p": p[pick], "conf": conf,
                    "nearest": nearest(inst, s), "latency_ms": rec.get("latency_ms"), "usage": rec.get("usage")})
        return pick

    policy.log = log
    return policy


def shortlist_policy(decider, tag="", version=2, top=3, gate=None):
    """Judgment inside a rule: the nearest-stop rule offers its `top` nearest stops (plus the depot when it's
    legal), and the model picks one. With `gate`, a pick the model gives less than `gate` probability goes to
    the rule's first choice instead."""
    log = []

    def policy(inst, s):
        stops = sorted((c for c in legal(inst, s) if c != 0), key=lambda c: dist(inst, s["at"], c))[:top]
        short = stops + ([0] if s["at"] != 0 else [])
        rule = stops[0] if stops else 0
        if len(short) == 1:
            return short[0]
        rng = random.Random("%s/%s/%d" % (inst["name"], tag, s["steps"]))
        opts = rng.sample(short, len(short))
        q = {"next": {"type": "choice",
                      "instructions": "Which move should the van make next so that the total distance of all trips is as small as possible?",
                      "criteria": {name(c): ("go back to the DEPOT and reload" if c == 0 else "go to " + name(c)) for c in opts}}}
        ans, rec = decider.ask(board(inst, s, opts, version), q, tag="%s/%s/%d" % (inst["name"], tag, s["steps"]))
        p = {c: ans["next"]["probabilities"].get(name(c), 0.0) for c in opts}
        pick = max(opts, key=lambda c: (p[c], -dist(inst, s["at"], c)))
        used = gate is None or p[pick] >= gate
        if not used:
            pick = rule
        log.append({"step": s["steps"], "n_opts": len(opts), "pick": pick, "p": p[pick], "conf": ans["next"].get("confidence"),
                    "nearest": rule, "used_model": used, "latency_ms": rec.get("latency_ms"), "usage": rec.get("usage")})
        return pick

    policy.log = log
    return policy


# ── Clarke & Wright savings (1964) ──────────────────────────────────────

def clarke_wright(inst):
    """Start with one trip per stop. Joining the trips of i and j saves d(0,i) + d(0,j) - d(i,j).
    Take the biggest savings first, and join whenever both are at the end of their trips and the load fits."""
    n, Q, dem = inst["n"], inst["Q"], inst["demand"]
    route = {i: [i] for i in range(1, n + 1)}           # stop -> its trip (shared list)
    load = {i: dem[i] for i in range(1, n + 1)}
    savings = sorted(((dist(inst, 0, i) + dist(inst, 0, j) - dist(inst, i, j), i, j)
                      for i in range(1, n + 1) for j in range(i + 1, n + 1)), reverse=True)
    for sv, i, j in savings:
        ri, rj = route[i], route[j]
        if ri is rj or load[ri[0]] + load[rj[0]] > Q:
            continue
        if ri[-1] != i:
            if ri[0] != i:
                continue
            ri.reverse()                                 # i at the end of its trip
        if rj[0] != j:
            if rj[-1] != j:
                continue
            rj.reverse()                                 # j at the start of its trip
        merged = ri + rj
        total = load[ri[0]] + load[rj[0]]
        for c in merged:
            route[c] = merged
        load[merged[0]] = load[merged[-1]] = total
    trips, seen = [], set()
    for i in range(1, n + 1):
        if id(route[i]) not in seen:
            seen.add(id(route[i]))
            trips.append(route[i])
    check(inst, trips)
    return trips


# ── OR-Tools routing solver ─────────────────────────────────────────────

def ortools(inst, seconds=1.0, initial=None, solutions=None):
    """Google OR-Tools: cheapest-arc start, then guided local search for `seconds`.
    `solutions` stops after that many solutions instead, which repeats exactly on any machine
    (a wall clock doesn't: a busy laptop gets less search done in a second).
    `initial` (a list of trips) warm-starts the search, e.g. from a decision model's route."""
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2
    n = inst["n"]
    m = len(initial) if initial else n
    vehicles = max(m, math.ceil(sum(inst["demand"]) / inst["Q"]) + 2)
    mgr = pywrapcp.RoutingIndexManager(n + 1, vehicles, 0)
    rt = pywrapcp.RoutingModel(mgr)
    D = [[round(dist(inst, a, b) * 1000) for b in range(n + 1)] for a in range(n + 1)]
    cb = rt.RegisterTransitCallback(lambda i, j: D[mgr.IndexToNode(i)][mgr.IndexToNode(j)])
    rt.SetArcCostEvaluatorOfAllVehicles(cb)
    dem = rt.RegisterUnaryTransitCallback(lambda i: inst["demand"][mgr.IndexToNode(i)])
    rt.AddDimensionWithVehicleCapacity(dem, 0, [inst["Q"]] * vehicles, True, "load")
    p = pywrapcp.DefaultRoutingSearchParameters()
    p.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    p.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    if solutions:
        p.solution_limit = solutions
        p.time_limit.FromSeconds(600)
    else:
        p.time_limit.FromMilliseconds(int(seconds * 1000))
    if initial:
        rt.CloseModelWithParameters(p)
        init = rt.ReadAssignmentFromRoutes([list(t) for t in initial] + [[]] * (vehicles - len(initial)), True)
        sol = rt.SolveFromAssignmentWithParameters(init, p)
    else:
        sol = rt.SolveWithParameters(p)
    trips = []
    for v in range(vehicles):
        i, t = rt.Start(v), []
        while not rt.IsEnd(i):
            node = mgr.IndexToNode(i)
            if node:
                t.append(node)
            i = sol.Value(rt.NextVar(i))
        if t:
            trips.append(t)
    check(inst, trips)
    return trips
