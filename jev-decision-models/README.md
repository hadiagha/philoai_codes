# Jev Decision Model: the code

This is the Python behind every number on screen in the PhiloAI video *Jev Decision Model: How It Works, Tested on 130,000+ Real Decisions*.

The video puts a decision model to work on three real planning jobs and compares it with classic solvers and rules:
- **delivery routes:** capacitated vehicle routing (CVRP), 40 maps with 10 or 50 stops;
- **hospital rosters:** nurse scheduling, 40 wards with 10 nurses × 1 week or 25 nurses × 4 weeks;
- **nurses' notes:** 60 messy notes turned into solver inputs, with a confidence gate.

The hosted model is Jev (TypeSafe); the open one is [Kev](https://github.com/jaredpalmer/kev), run locally. Together that's 134,368 model calls.

## Replay every number, with no API key

Every model answer is saved in `cache/` (gzipped). Replay mode reads only those answers and fails on any call that isn't saved, so the results below come back exactly, for free.

```bash
cd jev-decision-models
pip install ortools                     # the only library needed (OR-Tools and CP-SAT)
DECIDE_REPLAY=1 python3 run_cvrp.py     # routing study   → results/cvrp.json
DECIDE_REPLAY=1 python3 run_nsp.py      # rostering study → results/nsp.json
DECIDE_REPLAY=1 python3 notes.py --backend jev   # nurses' notes → results/notes_jev.json
DECIDE_REPLAY=1 python3 notes.py --backend kev
python3 export_slides.py slide_data.js           # every number the slides show, from the frozen final run
```

Run the files from inside this folder, because they import each other. The routing and rostering studies take a few minutes each, mostly OR-Tools and CP-SAT. Replaying on a second run reproduced every route length, gap and penalty exactly; only the wall-clock timings (`sec`) differ. The frozen results the video used are in `results/runs/2026-10-30c-final/`, and `export_slides.py` rebuilds every on-screen number from them.

To call the models yourself, set `OPENROUTER_API_KEY` for Jev, or serve Kev locally on port 8009 (see `decide.py`). New answers are appended to `cache/*.jsonl`.

## What each file does

| File | What it reproduces | In the video |
|---|---|---|
| [`decide.py`](decide.py) | One small client for decision models: send a state and typed questions, get probabilities back. Caches every answer, keyed by the exact request. | 04:52 a situation in, typed answers out |
| [`cvrp.py`](cvrp.py) | Vehicle routing as a Markov decision process: the state, the legal-move mask (the code owns the rules), the text board the model reads, the nearest-stop rule, Clarke–Wright savings (1964) and OR-Tools | 14:23 the routing problem · 15:23 the code owns the rules · 16:32 three rivals |
| [`run_cvrp.py`](run_cvrp.py) | The routing study: the calibration check on the best known routes, the scoreboard (Jev 15% / 26% above the best; Clarke–Wright 1.4% / 4.5%), best of 8, the warm start for OR-Tools, and the shortlist helper | 13:21 is its 62% honest? · 18:02 the scoreboard · 18:43 one map side by side · 19:22 head start · 22:33 shortlist |
| [`nsp.py`](nsp.py) | Nurse rostering as an MDP: hard rules, the penalty receipt, the greedy rule, Jev scoring every nurse, and the CP-SAT optimum | 20:17 the head nurse's Sunday night · 21:10 one ward, filled shift by shift |
| [`run_nsp.py`](run_nsp.py) | The rostering study: all 40 wards in penalty points above the proven best, and the shortlist helper with its 0.6 gate | 21:56 a one-line rule wins again · 22:33 shortlist |
| [`notes.py`](notes.py) | Sixty nurses' notes read into days off and shifts to avoid; the confidence gate (0.2–0.8 goes to a human, 15 flagged, all 6 mistakes caught); then CP-SAT rosters scored against what the nurses really asked (≈550 ignoring notes, 63 with Jev alone, 30 with Jev + the gate, the same as a perfect reading) | 23:47 sixty messy notes · 24:30 it knows when it doesn't know · 25:16 the roster it leads to |
| [`export_slides.py`](export_slides.py) | Every number the slides show, from the frozen final run and the cache: 134,368 calls, the bill (under $8), the median latency (about a quarter second, whatever the number of options), the first call by hand (S1 0.62, confidence 0.58), the calibration bins and the paired head-start test (11 wins, 8 losses) | 05:41 our first call · 06:49 the same quarter second · throughout |
| [`pilot.py`](pilot.py) | The first small pilot, run before the full study: one instance of each problem, every method, with timing and cost | (behind the scenes) |
| [`dump_examples.py`](dump_examples.py) | Saves real requests and answers (the exact text sent and the probabilities back) to `results/examples/` | 16:01 what the model actually reads |

`results/` holds the outputs the video used. `results/runs/` keeps the earlier runs as a lab notebook, including the warm-up incidents, so you can see how the final numbers were reached. `requirements-lock.txt` is the full environment the experiments ran in (Python 3.12, OR-Tools 9.15); you only need `ortools` to replay.

## Two things to know

- **The model is not deterministic.** Repeats use different tags (`rep0…rep2`, `sample0…sample7`), and the video reports the mean over them unless it says "best of".
- **The option order is shuffled in every call,** because these models tend to favor the first option in a list.

## Want the real-world versions?

Turning a messy business question into decisions, building your own environment (like the van and the ward), and search that plans ahead are all in the book [*Applied Reinforcement Learning: Business optimization and LLM fine-tuning*](https://www.manning.com/books/applied-reinforcement-learning) (Manning).
