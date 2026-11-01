"""One small client for decision models: send a state and typed questions, get typed probabilities back.

    from decide import Decider
    jev = Decider("jev")                      # hosted Jev (needs OPENROUTER_API_KEY)
    kev = Decider("kev")                      # open Kev served locally on :8009
    answers = jev.ask(state, questions, tag="cvrp/s0/step3/rep0")

Every response is cached in cache/<backend>[-<study>].jsonl (shipped gzipped as .jsonl.gz), keyed by the exact request plus `tag`.
The same tag returns the same answer, so every number in the video replays offline:
    DECIDE_REPLAY=1 python3 run_cvrp.py      # fails on any call that isn't cached
The model is not deterministic, so repeats use different tags (…/rep0, …/rep1, …).
"""
import gzip
import hashlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BACKENDS = {
    "jev": {"url": "https://openrouter.ai/api/alpha/decisions", "model": "typesafe/jev-1.13"},
    "kev": {"url": "http://127.0.0.1:8009/v1/systemone", "model": "kev-latest"},
}


def api_key():
    if os.environ.get("OPENROUTER_API_KEY"):
        return os.environ["OPENROUTER_API_KEY"]
    # in the studio repo the key sits in a git-ignored text file at the repo root
    for up in ("../../..", "../.."):
        path = os.path.join(HERE, up, "openrouter.txt")
        if os.path.exists(path):
            m = re.search(r"sk-or-[A-Za-z0-9_-]+", open(path).read())
            if m:
                return m.group(0)
    raise SystemExit("set OPENROUTER_API_KEY (or run with DECIDE_REPLAY=1 to use the cached answers)")


class Decider:
    def __init__(self, backend="jev", study="", cache_dir=os.path.join(HERE, "cache")):
        self.backend, self.cfg = backend, BACKENDS[backend]
        self.replay = os.environ.get("DECIDE_REPLAY") == "1"
        os.makedirs(cache_dir, exist_ok=True)
        self.path = os.path.join(cache_dir, backend + ("-" + study if study else "") + ".jsonl")
        self.cache, self.lock, self.pending = {}, threading.Lock(), {}
        for p, opener in ((self.path + ".gz", gzip.open), (self.path, open)):   # git ships the .gz; new answers append to .jsonl
            if os.path.exists(p):
                for line in opener(p, "rt"):
                    rec = json.loads(line)
                    self.cache[rec["key"]] = rec
        self.calls = self.hits = 0

    def key(self, state, questions, tag):
        blob = json.dumps([self.cfg["model"], state, questions, tag], sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode()).hexdigest()[:24]

    def ask(self, state, questions, tag=""):
        """-> (answers, record). record holds latency_ms, usage and cost."""
        k = self.key(state, questions, tag)
        with self.lock:
            if k in self.cache:
                self.hits += 1
                return self.cache[k]["answers"], self.cache[k]
            if self.replay:
                raise KeyError("not cached (replay mode): " + tag)
            # two runs can ask the same thing at once (e.g. a gated and an ungated policy sharing a prefix):
            # only one of them calls the model, the other waits, so the cache holds the one answer both used
            first = k not in self.pending
            ev = self.pending.setdefault(k, threading.Event())
        if not first:
            ev.wait()
            return self.ask(state, questions, tag)
        try:
            out, ms = self._post({"model": self.cfg["model"], "state": state, "questions": questions})
            rec = {"key": k, "tag": tag, "model": out.get("model"), "answers": out["answers"],
                   "usage": out.get("usage", {}), "latency_ms": ms}
            with self.lock:
                self.calls += 1
                self.cache[k] = rec
                with open(self.path, "a") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        finally:
            with self.lock:
                self.pending.pop(k).set()
        return rec["answers"], rec

    def _post(self, body):
        headers = {"Content-Type": "application/json"}
        if self.backend == "jev":
            headers["Authorization"] = "Bearer " + api_key()
        data = json.dumps(body).encode()
        for attempt in range(6):
            req = urllib.request.Request(self.cfg["url"], data=data, headers=headers)
            t = time.time()
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    return json.loads(r.read()), round((time.time() - t) * 1000)
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and attempt < 5:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError("HTTP %d: %s" % (e.code, e.read().decode()[:400]))
            except (urllib.error.URLError, TimeoutError):
                if attempt < 5:
                    time.sleep(2 ** attempt)
                    continue
                raise
