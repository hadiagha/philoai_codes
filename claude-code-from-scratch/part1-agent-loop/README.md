# Part 1 · The Agent Loop: the code

This is the code behind the PhiloAI video *Build a Claude Code Clone From Scratch, Part 1: The Agent Loop*.

**Cato v0.1** is the core every coding agent shares: a model, one tool (the shell) and a loop. In the video, it finds and fixes a real bug in a tiny shop project: 5 calls to the model, 10.1 seconds, $0.0204, and 4 of 4 tests passing.

## Run Cato yourself

You need Python 3.10 or newer and an [OpenRouter](https://openrouter.ai) key.

```bash
pip install httpx
export OPENROUTER_API_KEY=sk-or-...

cp -r shop /tmp/my-shop && cd /tmp/my-shop        # work on a copy: Cato really runs commands
python3 test_shop.py                              # 2 failed: the bug is real
python /path/to/cato.py                           # then type: The tests in test_shop.py fail. Find the bug and fix it.
```

Cato asks `Run it? [y/n]` before every command, so you stay in charge. To use another model, set `CATO_MODEL`, for example `CATO_MODEL=anthropic/claude-sonnet-5.5 python cato.py` (the model used in the video).

## Check the numbers, with no API key

`runs.json` is the frozen recording of every request and answer shown in the video. This rebuilds every number and text on the slides from it, for free:

```bash
python3 record_part1.py --export      # → numbers.json (5 turns, 10.1 s, $0.0204)
```

To record your own run instead, set `OPENROUTER_API_KEY` and run `python3 record_part1.py` (a few cents). Your numbers will differ a little, because the model's answers differ from run to run.

## Test the loop without a model

```bash
pip install pytest
python3 -m pytest -q test_part1.py    # a fake model drives the loop: no API calls, no cost
```

## What each file does

| File | What it is | In the video |
|---|---|---|
| [`hello_model.py`](hello_model.py) | One request to a language model through the OpenRouter API: JSON in, JSON out | 06:03 hello_model.py · 03:42 the model alone, with no tools |
| [`cato.py`](cato.py) | Cato v0.1, the whole agent in one file: the settings, the bash tool's form, `ask_model`, `run_bash` (ask first, then run), `agent_loop` and `main` | 10:12 the tool form · 13:30 the settings · 14:09 `ask_model` · 14:48 `run_bash` · 15:35 `agent_loop` · 16:29 `main` · 16:57 the whole program |
| [`shop/`](shop/) | The tiny shop with the real bug (the cart ignores how many you bought). `python3 test_shop.py` shows 2 failing tests until it's fixed | 17:35 a tiny shop, a real bug |
| [`runs.json`](runs.json) | The frozen recording: the model alone, the three "what's my name?" calls, and Cato's full run with every request, answer, timing and the exact terminal output | 07:29 it forgets · 08:10 tokens · 10:57 the filled-in form · 17:35 the real run · 18:36 the scorecard |
| [`record_part1.py`](record_part1.py) | Records `runs.json` (with a key) and rebuilds `numbers.json` from it (without one) | throughout |
| [`test_part1.py`](test_part1.py) | Tests for the loop, with a fake model | (behind the scenes) |

The run in `runs.json` happened in a temporary folder, which is why a temp path appears in it.
