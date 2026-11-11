# Part 2 · Tools That Read and Edit Code: the code

This is the code behind the PhiloAI video *Build a Claude Code Clone From Scratch, Part 2: Tools That Read and Edit Code*.

**Cato v0.2** replaces Part 1's single shell tool with six real tools: Read, Write, Edit, Bash, Glob and Grep. Every tool call goes through one path: look up the tool, check the form, run it, and trim the output. Errors go back to the model as text. Edit follows three rules: read first, match exactly, and match once.

In the video, Cato v0.2 fixes the same bug as Part 1, with the same model. It takes 4 calls, 8.5 seconds and $0.0276, and asks you 3 times. On the "twin" shop, where the buggy line appears twice, it changes only the line it meant to, and 5 of 5 tests pass.

## Run Cato yourself

You need Python 3.10 or newer and an [OpenRouter](https://openrouter.ai) key.

```bash
pip install -e .                         # from this folder; adds the `cato` command
export OPENROUTER_API_KEY=sk-or-...

cp -r shop /tmp/my-shop && cd /tmp/my-shop   # work on a copy: Cato really edits files and runs commands
python -m pytest -q                          # 2 failed: the bug is real
cato --model sonnet                          # then type: The tests in test_shop.py fail. Find the bug and fix it.
```

Read, Glob and Grep only look, so they run without asking. Write, Edit and Bash ask `Allow? [y/n]` first. `--model` takes `sonnet` (the model in the video), `opus`, `sol`, `terra`, `gemini`, or any OpenRouter model id.

To try the trap from the video, copy `twin/` instead of `shop/`.

## Check the numbers, with no API key

`runs.json` is the frozen recording of the two live runs in the video, with every request, answer, timing and the exact terminal output. `demos.json` holds every tool output shown on the slides. This rebuilds every number on the slides from those two files, for free:

```bash
python record_part2.py              # -> numbers.json
python record_part2.py --demos      # also re-run the free demos on fresh copies of the shop -> demos.json
```

`--demos` uses no API calls. It runs Cato's real tools on temporary copies of `shop/` and `twin/`: Part 1's `replace()` fix on the twin, Read, Glob, Grep and Write, the four Edit refusals plus the good edit, every error path, trimming, and the three ways to edit. Two things will differ a little from the recording: pytest's run time, and the order Glob lists files in, because Glob puts the newest files first and copying changes the dates.

To record your own live runs, set `OPENROUTER_API_KEY` and run `python record_part2.py --live` (about 6 cents). Your numbers will differ a little, because the model's answers vary from run to run. Part 1's numbers (v0.1) come from `../part1-agent-loop/runs.json`.

## Test it without a model

```bash
pip install pytest
python -m pytest -q tests        # a fake model drives the loop: no API calls, no cost
```

## What each file does

| File | What it is | In the video |
|---|---|---|
| [`cato/tools.py`](cato/tools.py) | The `Tool` record, the six tools, and the one path every call takes: `check_form`, `trim`, `run_tool` | 08:40 the Tool record · 09:13 the tool list · 11:18 `read_file` · 12:41 `glob_files` · 13:47 `grep_files` · 17:07 rule 1, read first · 17:45 `edit_file` · 19:41 `write_file` · 21:25 `check_form` · 22:04 `trim` · 22:51 `run_tool` · 23:22 `run_bash` |
| [`cato/agent.py`](cato/agent.py) | The loop from Part 1, now with `describe`, `confirm` and the new system prompt | 24:20 `describe` and `confirm` · 24:53 `agent_loop` · 25:34 the job description |
| [`cato/model.py`](cato/model.py) | One request to the model through OpenRouter, with short names for five models | 26:01 the package |
| [`cato/__main__.py`](cato/__main__.py) | The `cato` command | 26:01 the package · 31:03 run it yourself |
| [`shop/`](shop/) | The tiny shop with Part 1's bug (the cart ignores how many you bought), plus project notes and a built file for the demos | 26:39 the real run |
| [`twin/`](twin/) | The trap: the same buggy line also appears once, correctly, in `price_list_total` | 00:00 cold open · 28:02 the trap, live |
| [`runs.json`](runs.json) | The frozen recording of the two live runs (Claude Sonnet 5.5, $0.0557 in total) | 26:39 the real run · 27:19 v0.1 vs v0.2 · 28:02 the trap, live |
| [`demos.json`](demos.json) | Every tool output on the slides, from Cato's real tools | 00:00 cold open · 10:36 Read · 18:26 the rules say no · 20:19 the front desk |
| [`record_part2.py`](record_part2.py) | Records `demos.json` (free) and `runs.json` (with a key), and rebuilds `numbers.json` | throughout |
| [`tests/`](tests/) | Tests for the tools and the loop, with a fake model | (behind the scenes) |

The live runs happened in a temporary folder. In the recording, that folder's path is shortened to `…/shop`. That's the only change made to any output.
