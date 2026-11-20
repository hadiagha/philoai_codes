# Part 7 · How It All Connects: the code

This is the code behind the PhiloAI video *Build a Claude Code Clone From Scratch, Part 7: How It All Connects*.

There is **no new Cato code** in Part 7. `cato/` is Cato v0.6, the same as in [`part6-subagents-skills-mcp/`](../part6-subagents-skills-mcp/). This folder adds two things: a **trace** of one real request through every box, and a **small test** of Cato against the real Claude Code.

## 1. One request, traced through every function

In the video, one request is typed into Cato's real screen, in a fresh copy of the shop:

> Add a product called tea, for $3.50. Then run the tests.

It took 7 requests to the model, 6 tool calls and 3 permission questions, in 8.9 seconds, for $0.0162. Waiting for the model took 8.5 of those seconds; all six tools together took 0.26.

Then the same session was replayed from its recording, and every Cato function that started was logged, in order, with its file and the line that called it (Python's `sys.monitoring`, `PY_START`). That's 398 function starts in 11 files. A replay runs the same code as the live run. The only thing it skips is the network call.

```bash
pip install -r requirements.txt     # Python 3.12+ for the trace (sys.monitoring)

python record_part7.py --trace      # free: replay recordings/tea.jsonl in /tmp/shop, log every function -> trace.json
python record_part7.py              # free: rebuild every number on the slides -> numbers.json
python record_part7.py --live       # paid (about 2 cents): record a new tea session with Sonnet 5.5 -> runs.json
```

`/tmp/shop` must not exist yet (the script makes it and marks it as its own). `--live` needs `OPENROUTER_API_KEY`.

| File | What it is |
|---|---|
| `runs.json` | The live tea session: every event with its time, every request the model got (what was on it, how big), and the final screen |
| `recordings/tea.jsonl` | The same session's recording, for replay |
| `trace.json` | Every Cato function that started during the replay, in order, with who called it |
| `numbers.json` | Everything the slides show, rebuilt from the files above and the test results |

## 2. The test: Cato and Claude Code on eight small tasks

Eight small tasks, each in its own folder under `eval/tasks/`, with `task.md` (the request, word for word), `start/` (the starting files), and `check.py` (a script the agent never sees).

| # | Task |
|---|---|
| 01 | Fix a failing test in a temperature converter |
| 02 | Add a `--lines` command-line option, plus a test |
| 03 | Rename a function across a small package |
| 04 | Answer a question about a small codebase: who decides free shipping? |
| 05 | Fix a crash from its error message |
| 06 | Clean a messy CSV file: dates, case, duplicates |
| 07 | Find the first error in a log: who, when, how many |
| 08 | Tidy a downloads folder and write an index |

Every run starts in a new temporary folder with a fresh copy of `start/`, outside this repo. Both agents run in "accept edits" mode with the same 18 shell commands allowed (`COMMANDS` in `eval/run_eval.py`). Anything else is refused, by each agent's own gate, and nobody is there to say yes.

```bash
python eval/run_eval.py --verify                               # free, no AI: every check fails at the start and passes on our solution
python eval/run_eval.py --agents cato:terra --tasks 01         # Cato with GPT-6.1 Terra on task 01 (OpenRouter)
python eval/run_eval.py --agents cato:sonnet,cato:opus,cato:sol,cato:terra,cato:gemini,claude
```

`claude` runs the real Claude Code (`claude -p --model opus`) on your own Claude account. Results go to `eval/results/<time>.jsonl`, and `--budget` caps the OpenRouter spend of all Cato runs.

### The results from the video (one run each)

| Agent | Model | Passed | Cost, all 8 tasks |
|---|---|---|---|
| Claude Code 2.1.326 | Claude Opus 5.5 | 8/8 | $1.08 |
| Cato v0.6 | GPT-6.1 Sol | 8/8 | $0.099 |
| Cato v0.6 | GPT-6.1 Terra | 8/8 | $0.045 |
| Cato v0.6 | Gemini 4 Argon | 7/8 | $0.160 |
| Cato v0.6 | Claude Opus 5.5 | 6/8 | $0.291 |
| Cato v0.6 | Claude Sonnet 5.5 | 5/8 | $0.129 |

Claude Code's cost is its own figure at list prices (it ran on a subscription). Cato's costs are what OpenRouter billed.

Every Cato failure looked the same: the gate refused one shell command (a `for` loop, a script typed inline, `printf`, or a line continuation with `\`), and the model stopped and asked what to do. That's what Cato's refusal tells it: "The user said no. Ask them what to do instead." (`cato/permissions.py`, from Part 4). In a run with nobody watching, no one answers. On task 08, Claude Code with the same Opus model was refused five times, kept looking for an allowed way, and passed in 13 turns.

| File | What it is |
|---|---|
| `eval.jsonl` | The frozen results: one line per run, with the check's verdict, turns, time, cost, tokens, and the commands Claude Code refused |
| `eval_sessions/` | The 40 Cato sessions, recorded, so you can read every request and answer |
| `eval_refusals.json` | The shell commands Cato's gate refused in the failed runs, found by replaying those sessions |

### What this test can't tell you

- Eight small tasks, written by me. Real work is bigger and messier.
- One run each. A rerun could flip a pass or a fail ("run each task more than once", Sarkis, Anthropic, 2026).
- The rules shaped the result. With everything allowed, the scores would change.
- Different models have different prices, so the cost gap isn't only the harness.

Cato talks to models through [OpenRouter](https://openrouter.ai). Claude and Claude Code are products of Anthropic. This is an independent educational project, not affiliated with or endorsed by Anthropic.
