"""Nurse rostering ("Rest + Requests") as a Markov decision process, plus the methods we compare.

Every day has three shifts, Morning, Afternoon and Night, each needing a fixed number of nurses.

    hard rules (the code enforces them; nothing can break them)
      1. exact coverage: every shift gets exactly the nurses it needs
      2. at most one shift per nurse per day
      3. rest: no Night followed by next-day Morning
    soft goals (the penalty to keep small)
      10 points for every shift a nurse works on a day they asked off
       4 points for every shift of the type a nurse asked to avoid (some nurses avoid Mornings, some Nights)
       5 points for every shift of difference between the busiest and the least busy nurse

As an MDP we fill the roster one shift at a time, day by day:
    state  = which shift we're filling, and each nurse's history (shifts so far, last shift, wishes)
    action = which nurses work this shift
    mask   = code removes nurses that would break a hard rule
    reward = minus the penalty
"""
import random

SHIFTS = ["Morning", "Afternoon", "Night"]
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
SIZES = {"small": {"nurses": 10, "days": 7, "cover": [3, 2, 2], "requests": 2},
         "medium": {"nurses": 25, "days": 28, "cover": [7, 6, 4], "requests": 6}}
REQUEST, AVOID, FAIR = 10, 4, 5


def make_instance(size, seed):
    cfg = SIZES[size]
    rng = random.Random("nsp/%s/%d" % (size, seed))
    D = cfg["days"]
    weight = [3 if d % 7 >= 4 else 1 for d in range(D)]       # Fri, Sat, Sun are the popular days off
    off = []
    for _ in range(cfg["nurses"]):
        days = set()
        while len(days) < cfg["requests"]:
            days.add(rng.choices(range(D), weight)[0])
        off.append(sorted(days))
    avoid = [rng.choices([None, 0, 2], [2, 1, 2])[0] for _ in range(cfg["nurses"])]   # 40% none, 20% Mornings, 40% Nights
    return {"name": "nsp-%s-s%d" % (size, seed), "size": size, "seed": seed,
            "N": cfg["nurses"], "D": D, "cover": cfg["cover"], "off": off, "avoid": avoid}


def nurse(i):
    return "N%02d" % (i + 1)


def day(d):
    return "Day %d (%s)" % (d + 1, DAYS[d % 7])


def penalty(inst, roster):
    """roster[d][s] = list of nurses. -> (total, broken day-off requests, avoided shifts worked, max load - min load)"""
    load = [0] * inst["N"]
    broken = avoided = 0
    for d in range(inst["D"]):
        for s in range(3):
            for i in roster[d][s]:
                load[i] += 1
                broken += d in inst["off"][i]
                avoided += inst["avoid"][i] == s
    spread = max(load) - min(load)
    return REQUEST * broken + AVOID * avoided + FAIR * spread, broken, avoided, spread


def check(inst, roster):
    for d in range(inst["D"]):
        on = [i for s in range(3) for i in roster[d][s]]
        assert [len(roster[d][s]) for s in range(3)] == inst["cover"], "coverage"
        assert len(on) == len(set(on)), "one shift per day"
        if d:
            assert not set(roster[d - 1][2]) & set(roster[d][0]), "rest after night"
    return True


# ── the MDP ─────────────────────────────────────────────────────────────

def start(inst):
    return {"d": 0, "s": 0, "roster": [[[] for _ in range(3)] for _ in range(inst["D"])], "load": [0] * inst["N"]}


def legal(inst, st):
    d, s, R = st["d"], st["s"], st["roster"]
    busy = {i for k in range(3) for i in R[d][k]}
    if s == 0 and d:
        busy |= set(R[d - 1][2])                             # rest rule
    return [i for i in range(inst["N"]) if i not in busy]


def step(inst, st, picks):
    R = [[list(x) for x in r] for r in st["roster"]]
    R[st["d"]][st["s"]] = sorted(picks)
    load = list(st["load"])
    for i in picks:
        load[i] += 1
    d, s = (st["d"], st["s"] + 1) if st["s"] < 2 else (st["d"] + 1, 0)
    return {"d": d, "s": s, "roster": R, "load": load}


def rollout(inst, policy):
    st = start(inst)
    while st["d"] < inst["D"]:
        opts = legal(inst, st)
        k = inst["cover"][st["s"]]
        picks = policy(inst, st, opts, k)
        assert len(set(picks)) == k and set(picks) <= set(opts)
        st = step(inst, st, picks)
    check(inst, st["roster"])
    return st["roster"]


def last_shift(st, i):
    d = st["d"]
    for s in range(st["s"] - 1, -1, -1):
        if i in st["roster"][d][s]:
            return "today"
    if d and any(i in st["roster"][d - 1][s] for s in range(3)):
        return next(SHIFTS[s] for s in range(3) if i in st["roster"][d - 1][s])
    return "off"


# ── the board as text (what the decision model reads) ───────────────────

def board(inst, st, opts, version=1):
    d, s, k = st["d"], st["s"], inst["cover"][st["s"]]
    total = inst["D"] * sum(inst["cover"])
    done = sum(st["load"])
    lines = [
        "Hospital ward roster for %d nurses over %d days. Shifts: Morning, Afternoon, Night." % (inst["N"], inst["D"]),
        "The code already enforces: exact coverage, at most one shift per nurse per day, and no Night followed by next-day Morning.",
        "Penalty to keep small: %d points each time a nurse works on a day they asked off, %d points each time a nurse works "
        "a shift type they asked to avoid, and %d points for every shift of difference between the busiest and the least busy "
        "nurse at the end." % (REQUEST, AVOID, FAIR),
        "Now filling: %s, %s shift. It needs %d nurse%s." % (day(d), SHIFTS[s], k, "" if k == 1 else "s"),
        "Shifts filled so far: %d of %d. At the end each nurse will average %.1f shifts." % (done, total, total / inst["N"]),
        "Nurses who can work this shift:",
    ]
    for i in opts:
        later = [DAYS[x % 7] + ("" if inst["D"] <= 7 else " (day %d)" % (x + 1)) for x in inst["off"][i] if x > d]
        extra = ""
        if version >= 2:   # v2: the facts a head nurse would check, worked out by code
            now = REQUEST * (d in inst["off"][i]) + AVOID * (inst["avoid"][i] == s)
            free = sum(1 for x in range(d + 1, inst["D"]) if x not in inst["off"][i])
            fair = done / inst["N"]
            extra = " Penalty if picked now: %d. Fair share so far: %.1f shifts. Later days they can work without penalty: %d." % (now, fair, free)
        lines.append("%s: %d shifts so far. Asked for today off: %s. Avoids: %s. Days off asked later: %s. Last worked: %s.%s" % (
            nurse(i), st["load"][i], "YES" if d in inst["off"][i] else "no",
            SHIFTS[inst["avoid"][i]] + "s" if inst["avoid"][i] is not None else "nothing", ", ".join(later) or "none",
            "yesterday " + last_shift(st, i) if last_shift(st, i) in SHIFTS else last_shift(st, i), extra))
    return "\n".join(lines)


# ── policies ────────────────────────────────────────────────────────────

def greedy(inst, st, opts, k):
    """The classic rule: pick whoever costs the least penalty right now, then whoever has worked least."""
    cost = lambda i: REQUEST * (st["d"] in inst["off"][i]) + AVOID * (inst["avoid"][i] == st["s"])
    return sorted(opts, key=lambda i: (cost(i), st["load"][i], i))[:k]


LEVELS = ["Very bad", "Bad", "Okay", "Good", "Very good"]


def model_policy(decider, mode="score", tag="", version=1, sample=False):
    """mode 'score' = one score question per legal nurse, all in one call; mode 'choice' = one question over all
    legal nurses, and the k most likely get the shift. sample=True draws the k nurses from the choice probabilities."""
    log = []

    def policy(inst, st, opts, k):
        rng = random.Random("%s/%s/%d/%d" % (inst["name"], tag, st["d"], st["s"]))
        opts = rng.sample(opts, len(opts))                   # shuffle: the model leans towards the first option
        state = board(inst, st, opts, version)
        t = "%s/%s/%d/%d" % (inst["name"], tag, st["d"], st["s"])
        if mode == "choice":
            q = {"pick": {"type": "choice",
                          "instructions": "Which nurse is the best pick for this shift, to keep the total penalty of the whole roster small?",
                          "criteria": {nurse(i): "assign " + nurse(i) for i in opts}}}
            ans, rec = decider.ask(state, q, tag=t)
            p = {i: ans["pick"]["probabilities"].get(nurse(i), 0.0) for i in opts}
        else:
            q = {nurse(i): {"type": "score",
                            "instructions": "How good a choice is %s for this shift, to keep the total penalty of the whole roster small?" % nurse(i),
                            "criteria": LEVELS} for i in opts}
            ans, rec = decider.ask(state, q, tag=t)
            p = {i: ans[nurse(i)]["score"] for i in opts}
        if sample and mode == "choice":
            pool, picks = list(opts), []
            for _ in range(k):                               # draw k nurses without replacement
                w = [p[i] + 1e-6 for i in pool]
                pick = rng.choices(pool, w)[0]
                picks.append(pick)
                pool.remove(pick)
        else:
            picks = sorted(opts, key=lambda i: (-p[i], st["load"][i], i))[:k]
        log.append({"d": st["d"], "s": st["s"], "n_opts": len(opts), "picks": picks,
                    "greedy_agree": len(set(picks) & set(greedy(inst, st, opts, k))) / k,
                    "latency_ms": rec.get("latency_ms"), "usage": rec.get("usage")})
        return picks

    policy.log = log
    return policy


def shortlist_policy(decider, tag="", version=2, top=3, gate=None):
    """Judgment inside a rule: the shift's places are filled one at a time. For each place the greedy rule offers
    its `top` best nurses, and the model picks one. With `gate`, a pick the model gives less than `gate`
    probability goes to the rule's first choice instead."""
    log = []

    def policy(inst, st, opts, k):
        rule_order = greedy(inst, st, opts, len(opts))
        picks = []
        for j in range(k):
            left = [i for i in rule_order if i not in picks]
            short = left[:top]
            t = "%s/%s/%d/%d/%d" % (inst["name"], tag, st["d"], st["s"], j)
            if len(short) == 1:
                picks.append(short[0])
                continue
            rng = random.Random(t)
            short = rng.sample(short, len(short))
            state = board(inst, st, short, version)
            if picks:
                state += "\nAlready chosen for this shift: %s. Choose the next nurse." % ", ".join(nurse(i) for i in picks)
            q = {"pick": {"type": "choice",
                          "instructions": "Which nurse is the best pick for this shift, to keep the total penalty of the whole roster small?",
                          "criteria": {nurse(i): "assign " + nurse(i) for i in short}}}
            ans, rec = decider.ask(state, q, tag=t)
            p = {i: ans["pick"]["probabilities"].get(nurse(i), 0.0) for i in short}
            pick = max(short, key=lambda i: (p[i], -left.index(i)))
            used = gate is None or p[pick] >= gate
            if not used:
                pick = left[0]
            picks.append(pick)
            log.append({"d": st["d"], "s": st["s"], "j": j, "n_opts": len(short), "pick": pick, "p": p[pick],
                        "rule": left[0], "used_model": used, "latency_ms": rec.get("latency_ms"), "usage": rec.get("usage")})
        return picks

    policy.log = log
    return policy


# ── simulated annealing on top of any roster ────────────────────────────

def anneal(inst, roster, iters=20000, seed=0, t0=10.0, t1=0.1):
    """Move one nurse out of a shift and another (free that day, rest rule kept) in.
    Keep better rosters; keep worse ones with a probability that shrinks over time."""
    rng = random.Random("anneal/%s/%d" % (inst["name"], seed))
    R = [[list(x) for x in r] for r in roster]
    cur = best = penalty(inst, R)[0]
    bestR = [[list(x) for x in r] for r in R]
    for it in range(iters):
        T = t0 * (t1 / t0) ** (it / iters)
        d, s = rng.randrange(inst["D"]), rng.randrange(3)
        out = rng.choice(R[d][s])
        on = {i for k in range(3) for i in R[d][k]}
        free = [i for i in range(inst["N"]) if i not in on
                and not (s == 0 and d and i in R[d - 1][2])
                and not (s == 2 and d + 1 < inst["D"] and i in R[d + 1][0])]
        if not free:
            continue
        inn = rng.choice(free)
        R[d][s][R[d][s].index(out)] = inn
        new = penalty(inst, R)[0]
        if new <= cur or rng.random() < pow(2.718281828, (cur - new) / T):
            cur = new
            if cur < best:
                best, bestR = cur, [[list(x) for x in r] for r in R]
        else:
            R[d][s][R[d][s].index(inn)] = out
    check(inst, bestR)
    return bestR


# ── OR-Tools CP-SAT ─────────────────────────────────────────────────────

def cpsat(inst, seconds=10.0, workers=8, seed=0):
    from ortools.sat.python import cp_model
    N, D, C = inst["N"], inst["D"], inst["cover"]
    m = cp_model.CpModel()
    x = {(i, d, s): m.NewBoolVar("x%d_%d_%d" % (i, d, s)) for i in range(N) for d in range(D) for s in range(3)}
    for d in range(D):
        for s in range(3):
            m.Add(sum(x[i, d, s] for i in range(N)) == C[s])
        for i in range(N):
            m.Add(sum(x[i, d, s] for s in range(3)) <= 1)
            if d + 1 < D:
                m.Add(x[i, d, 2] + x[i, d + 1, 0] <= 1)
    load = [sum(x[i, d, s] for d in range(D) for s in range(3)) for i in range(N)]
    hi, lo = m.NewIntVar(0, D, "hi"), m.NewIntVar(0, D, "lo")
    for i in range(N):
        m.Add(hi >= load[i])
        m.Add(lo <= load[i])
    broken = sum(x[i, d, s] for i in range(N) for d in inst["off"][i] for s in range(3))
    avoided = sum(x[i, d, inst["avoid"][i]] for i in range(N) if inst["avoid"][i] is not None for d in range(D))
    m.Minimize(REQUEST * broken + AVOID * avoided + FAIR * (hi - lo))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.num_workers = workers
    solver.parameters.random_seed = seed
    status = solver.Solve(m)
    R = [[[i for i in range(N) if solver.Value(x[i, d, s])] for s in range(3)] for d in range(D)]
    check(inst, R)
    return R, solver.StatusName(status), solver.BestObjectiveBound()
