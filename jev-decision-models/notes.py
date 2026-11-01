"""Showcase: a decision model as the translator in front of a solver.

Sixty nurses each leave a short, messy note about next week. A solver can't read notes, so the
decision model turns each one into the solver's inputs: which days off, and which shift to avoid.
Notes it isn't sure about go to a human (the confidence gate). Then CP-SAT builds the rosters.

    python3 notes.py
    DECIDE_REPLAY=1 python3 notes.py
"""
import argparse
import json
import statistics as S

import nsp
from decide import Decider

WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# (note, days off, shift to avoid). Written by hand; the labels are what a careful head nurse would read.
NOTES = [
    ("Can't do Tuesday, dentist at 10.", ["Tue"], None),
    ("No nights please, I have exams this month.", [], "Night"),
    ("My sister's wedding is on Saturday so I need the whole weekend off.", ["Sat", "Sun"], None),
    ("Anything works for me this week!", [], None),
    ("Mornings are really hard with the school run. Afternoons or nights are fine.", [], "Morning"),
    ("I'd like Friday off if possible. Also no night shifts.", ["Fri"], "Night"),
    ("Off Mon and Wed, physio appointments.", ["Mon", "Wed"], None),
    ("I can work Thursday, just not Wednesday.", ["Wed"], None),
    ("pls no mornings, and i need thurs off for my kid's recital", ["Thu"], "Morning"),
    ("Happy to pick up extra shifts. Only thing: not Sunday, church.", ["Sun"], None),
    ("Away from Friday to Sunday, family trip.", ["Fri", "Sat", "Sun"], None),
    ("Nights suit me best actually, avoid giving me afternoons if you can.", [], "Afternoon"),
    ("Monday is my daughter's birthday, I want to be home with her.", ["Mon"], None),
    ("Not working weekends this time please.", ["Sat", "Sun"], None),
    ("No preferences.", [], None),
    ("Could I have Wednesday off? Moving apartments.", ["Wed"], None),
    ("I'm fine with any day but I really can't do nights anymore, doctor's orders.", [], "Night"),
    ("Need Saturday off. Sunday is fine.", ["Sat"], None),
    ("Off on the first day of the week please.", ["Mon"], None),
    ("I've worked a lot of nights lately, could I avoid them this week?", [], "Night"),
    ("Friday off for a funeral.", ["Fri"], None),
    ("Early shifts are rough for me, I take the first bus at 6. Days: no restrictions.", [], "Morning"),
    ("Can't work Tuesday or Saturday.", ["Tue", "Sat"], None),
    ("Any shift, any day.", [], None),
    ("I'll be at a conference Wed to Thu.", ["Wed", "Thu"], None),
    ("Afternoons clash with my kids' pickup, so mornings or nights only.", [], "Afternoon"),
    ("Sunday off please, and if possible no nights.", ["Sun"], "Night"),
    ("I could do the weekend, but Monday I'm out.", ["Mon"], None),
    ("No mornings. Also off Fri.", ["Fri"], "Morning"),
    ("Please avoid scheduling me on Thursday.", ["Thu"], None),
    ("Visiting my parents Saturday, back the same night.", ["Sat"], None),
    ("Nothing special this week, thanks!", [], None),
    ("I need Monday and Tuesday off, and I prefer not to do nights.", ["Mon", "Tue"], "Night"),
    ("Would love Sunday off, it's my anniversary.", ["Sun"], None),
    ("Wednesday's out for me, jury duty.", ["Wed"], None),
    ("I'm okay with nights, mornings, whatever. Just not afternoons, I have therapy.", [], "Afternoon"),
    ("Off Thu + Fri pls.", ["Thu", "Fri"], None),
    ("Saturday I'm running a marathon.", ["Sat"], None),
    ("Can I get Tuesday? Off, I mean.", ["Tue"], None),
    ("No night shifts this week, my partner is traveling and I'm alone with the baby.", [], "Night"),
    ("Working is fine every day except the weekend days.", ["Sat", "Sun"], None),
    ("Morning shifts are not great for me, but days are flexible.", [], "Morning"),
    ("I'm free all week.", [], None),
    ("Need off on Fri & Sat for a family event.", ["Fri", "Sat"], None),
    ("Thursday is a no for me.", ["Thu"], None),
    ("Please don't put me on nights. I'd also like Monday off.", ["Mon"], "Night"),
    ("I can take extra afternoons. Avoid mornings if you can.", [], "Morning"),
    ("Sunday please, off.", ["Sun"], None),
    ("Wed off, kid's surgery.", ["Wed"], None),
    ("Nights are fine, mornings are fine, I'll work anything except Tuesday.", ["Tue"], None),
    ("Out of town Friday and Saturday.", ["Fri", "Sat"], None),
    ("I'd rather not do afternoons. Days off: Sunday.", ["Sun"], "Afternoon"),
    ("Monday off pls, and no nights.", ["Mon"], "Night"),
    ("I don't mind which days. Could you keep me off nights though?", [], "Night"),
    ("Off Saturday.", ["Sat"], None),
    ("Any day but Wednesday or Friday.", ["Wed", "Fri"], None),
    ("No requests.", [], None),
    ("Not available Mon, Tue, Wed, I'm on a course.", ["Mon", "Tue", "Wed"], None),
    ("Mornings please avoid. Weekend off if possible.", ["Sat", "Sun"], "Morning"),
    ("Tuesday off. I'm happy doing nights.", ["Tue"], None),
]
AVOID = {"none": None, "Morning": "Morning", "Afternoon": "Afternoon", "Night": "Night"}
GATE = (0.2, 0.8)       # a day answer between these counts as unsure
GATE_CHOICE = 0.5       # the avoid answer is unsure below this probability
SEEDS = 10              # solver seeds per roster (ties between equally good rosters)


def questions():
    q = {d: {"type": "noul", "instructions": "Does the nurse ask to have %s off, so they don't work at all that day?" % full,
             "criteria": {"true": "asks for %s off" % full, "false": "does not ask for %s off" % full}}
         for d, full in zip(WEEK, DAY_NAMES)}
    q["avoid"] = {"type": "choice", "instructions": "Which shift type does the nurse ask to avoid next week?",
                  "criteria": {"none": "no shift type to avoid", "Morning": "avoids Morning shifts",
                               "Afternoon": "avoids Afternoon shifts", "Night": "avoids Night shifts"}}
    return q


def read_note(decider, i, text):
    state = "A nurse's note to the head nurse about the roster for next week (Monday to Sunday):\n\"%s\"" % text
    ans, rec = decider.ask(state, questions(), tag="notes/%d" % i)
    p_days = {d: ans[d]["noul"] for d in WEEK}
    probs = ans["avoid"]["probabilities"]
    avoid = max(probs, key=probs.get)
    unsure = [d for d in WEEK if GATE[0] < p_days[d] < GATE[1]] + (["avoid"] if probs[avoid] < GATE_CHOICE else [])
    return {"off": [d for d in WEEK if p_days[d] >= 0.5], "avoid": AVOID[avoid], "p_days": p_days,
            "p_avoid": probs[avoid], "unsure": unsure, "latency_ms": rec.get("latency_ms"), "cost": (rec.get("usage") or {}).get("cost", 0)}


def roster_inst(ward, wishes):
    """One ward = 10 nurses for one week, the small roster size. wishes[i] = (days off, avoided shift)."""
    cfg = nsp.SIZES["small"]
    return {"name": "notes-ward%d" % ward, "size": "small", "seed": ward, "N": len(wishes), "D": 7, "cover": cfg["cover"],
            "off": [sorted(WEEK.index(d) for d in off) for off, _ in wishes],
            "avoid": [None if a is None else nsp.SHIFTS.index(a) for _, a in wishes]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="jev")
    a = ap.parse_args()
    dec = Decider(a.backend, study="notes")
    reads = [read_note(dec, i, t) for i, (t, _, _) in enumerate(NOTES)]
    rows = []
    for (text, off, avoid), r in zip(NOTES, reads):
        day_ok = sum((d in off) == (d in r["off"]) for d in WEEK)
        rows.append({"note": text, "true_off": off, "true_avoid": avoid, "read_off": r["off"], "read_avoid": r["avoid"],
                     "days_right": day_ok, "avoid_right": avoid == r["avoid"],
                     "all_right": day_ok == 7 and avoid == r["avoid"], "unsure": r["unsure"],
                     "p_days": r["p_days"], "p_avoid": r["p_avoid"], "latency_ms": r["latency_ms"], "cost": r["cost"]})
    n = len(rows)
    flagged = [x for x in rows if x["unsure"]]
    auto = [x for x in rows if not x["unsure"]]
    summary = {
        "notes": n,
        "fields_right_%": 100 * sum(x["days_right"] + x["avoid_right"] for x in rows) / (8 * n),
        "notes_all_right_%": 100 * sum(x["all_right"] for x in rows) / n,
        "flagged_for_a_human": len(flagged),
        "auto_notes_all_right_%": 100 * sum(x["all_right"] for x in auto) / max(1, len(auto)),
        "flagged_notes_all_right_%": 100 * sum(x["all_right"] for x in flagged) / max(1, len(flagged)),
        "median_latency_ms": S.median(x["latency_ms"] for x in rows if x["latency_ms"]),
        "total_cost_usd": sum(x["cost"] for x in rows),
    }
    # rosters: 6 wards of 10 nurses. Score every roster against the TRUE wishes.
    truth = [(off, av) for _, off, av in NOTES]
    read = [(r["off"], r["avoid"]) for r in reads]
    gated = [t if x["unsure"] else rd for t, rd, x in zip(truth, read, rows)]       # unsure notes: a human reads them
    nothing = [([], None)] * n
    # Several rosters tie on the wishes the solver is given, and they can score differently on the true wishes.
    # So each input is solved with SEEDS solver seeds (one worker each, so every run repeats exactly) and averaged.
    wards = []
    for w in range(n // 10):
        sl = slice(10 * w, 10 * w + 10)
        true_inst = roster_inst(w, truth[sl])
        out = {}
        for name, wishes in [("ignore_notes", nothing), ("model_reads", read), ("model_plus_human", gated), ("perfect_reading", truth)]:
            out[name] = [nsp.penalty(true_inst, nsp.cpsat(roster_inst(w, wishes[sl]), 10, workers=1, seed=sd)[0])[0] for sd in range(SEEDS)]
        wards.append(out)
    totals = {k: [sum(w[k][sd] for w in wards) for sd in range(SEEDS)] for k in wards[0]}
    summary["roster_penalty_true_wishes"] = {k: S.mean(v) for k, v in totals.items()}
    summary["roster_penalty_range"] = {k: [min(v), max(v)] for k, v in totals.items()}
    json.dump({"summary": summary, "notes": rows, "wards": wards}, open("results/notes_%s.json" % a.backend, "w"), indent=1)
    print(json.dumps(summary, indent=1))
    for x in rows:
        if not x["all_right"]:
            print("  WRONG%s: %r -> off %s avoid %s (true %s / %s)" % (" (flagged)" if x["unsure"] else "", x["note"],
                  x["read_off"], x["read_avoid"], x["true_off"], x["true_avoid"]))


if __name__ == "__main__":
    main()
