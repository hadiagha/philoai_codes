"""Save real requests and answers (state + questions + the cached answer) for the write-up and the slides.

    DECIDE_REPLAY=1 python3 dump_examples.py

Replays the cache, so it costs nothing. Writes results/examples/<study>_<method>.json:
the first decision of seed 0 for each board version and question mode, exactly as sent.
"""
import json
import os

os.environ.setdefault("DECIDE_REPLAY", "1")

import cvrp
import notes
import nsp
from decide import Decider


class Recorder:
    """Wraps a Decider and keeps the first request it sees."""
    def __init__(self, decider):
        self.d, self.first = decider, None

    def ask(self, state, questions, tag=""):
        ans, rec = self.d.ask(state, questions, tag)
        if self.first is None:
            self.first = {"tag": tag, "model": rec.get("model"), "state": state, "questions": questions,
                          "answers": ans, "latency_ms": rec.get("latency_ms"), "usage": rec.get("usage")}
        return ans, rec


def save(name, rec):
    os.makedirs("results/examples", exist_ok=True)
    json.dump(rec, open("results/examples/%s.json" % name, "w"), indent=1, ensure_ascii=False)
    print("  results/examples/%s.json  (%d state chars, %d questions)" % (name, sum(map(len, rec["state"])) if isinstance(rec["state"], list) else len(rec["state"]), len(rec["questions"])))


def main():
    for backend in ("jev", "kev"):
        for size, n in (("small", 10), ("medium", 50)):
            inst = cvrp.make_instance(n, 0)
            for mode, ver in (("choice", 1), ("choice", 2), ("score", 2)):
                if backend == "kev" and ver == 1:
                    continue
                r = Recorder(Decider(backend))
                try:
                    pol = cvrp.model_policy(r, mode=mode, tag="full/%s/v%d/rep0" % (mode, ver), version=ver)
                    pol(inst, cvrp.start(inst))
                except KeyError:
                    continue
                save("cvrp_%s_%s_%s_v%d" % (size, backend, mode, ver), r.first)
            inst = nsp.make_instance(size, 0)
            for mode, ver in (("score", 1), ("score", 2), ("choice", 2)):
                if backend == "kev" and ver == 1:
                    continue
                r = Recorder(Decider(backend, study="nsp"))
                st = nsp.start(inst)
                try:
                    pol = nsp.model_policy(r, mode=mode, tag="full/%s/v%d/rep0" % (mode, ver), version=ver)
                    pol(inst, st, nsp.legal(inst, st), inst["cover"][0])
                except KeyError:
                    continue
                save("nsp_%s_%s_%s_v%d" % (size, backend, mode, ver), r.first)
        r = Recorder(Decider(backend, study="notes"))
        try:
            notes.read_note(r, 0, notes.NOTES[0][0])
            save("notes_%s" % backend, r.first)
        except KeyError:
            pass


if __name__ == "__main__":
    main()
