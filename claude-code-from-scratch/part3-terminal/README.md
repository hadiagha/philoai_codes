# Part 3 · A Terminal Like Claude Code: the code

This is the code behind the PhiloAI video *Build a Claude Code Clone From Scratch, Part 3: A Terminal Like Claude Code*.

**Cato v0.3** gets a real screen. The model's answer streams in piece by piece. The loop stops printing and hands out events instead, and the screen just listens to them: a spinner, the words so far, a summary of each tool, a status line and slash commands. The same events also drive headless mode (`cato -p`). Ctrl+C stops the answer without losing your chat, because every tool request still gets an answer. A cost limit stops the loop before it spends too much. You can record a session once and replay it for free.

In the video, Cato v0.2 and v0.3 get the same question, with the same model. v0.2 shows nothing for about 5 seconds and then prints the whole answer. v0.3 shows its first words after about 1 second and finishes at about the same time. It's the same wait, but it feels faster. Then v0.3 fixes the shop's bug from Parts 1 and 2: 4 calls, 6.1 seconds and $0.0217. It asks you 3 times, and 4 of 4 tests pass.

The six tools in `cato/tools.py` are exactly the same as in Part 2.

## Run Cato yourself

You need Python 3.10 or newer and an [OpenRouter](https://openrouter.ai) key.

```bash
pip install -e .                         # from this folder; adds the `cato` command
export OPENROUTER_API_KEY=sk-or-...

cp -r shop /tmp/my-shop && cd /tmp/my-shop   # work on a copy: Cato really edits files and runs commands
python -m pytest -q                          # 2 failed: the bug is real
cato --model sonnet                          # the full screen; then type: The tests in test_shop.py fail. Find the bug and fix it.
```

Then try the rest of what the video shows:

```bash
cato -p "Explain this project" --json        # headless: no screen, the answer and the numbers as JSON
cato --model sonnet --max-cost 0.01          # the loop stops once the task has cost more than a cent
cato --record my.jsonl                       # save every answer the model gives...
cato --replay my.jsonl                       # ...then play the same session back, for free
```

On the screen, type `/help` for the slash commands (`/model`, `/cost`, `/clear`, `/exit`). Press Ctrl+C while Cato is working to stop it and tell it what to do instead.

Read, Glob and Grep only look, so they run without asking. Write, Edit and Bash ask `Allow? (y/n)` first. `--model` takes `sonnet` (the model in the video), `opus`, `sol`, `terra`, `gemini`, or any OpenRouter model id.

## Watch the recorded fix, with no API key

`recordings/fix.jsonl` is the real session from the video. Replaying it needs no key and costs nothing. Cato's real tools still run, so it really fixes your copy of the shop:

```bash
REC="$PWD/recordings/fix.jsonl"              # from this folder
cp -r shop /tmp/replay-shop && cd /tmp/replay-shop
cato -p "The tests in test_shop.py fail. Find the bug and fix it." --replay "$REC" --yes --json
```

## Check the numbers, with no API key

`runs.json` is the frozen recording of the live runs in the video, with every streamed line and the time it arrived, every event, and the exact screen. `demos.json` holds everything else on the slides. This rebuilds every number on the slides from those two files, for free:

```bash
pip install -r requirements.txt
python record_part3.py              # -> numbers.json
python record_part3.py --demos      # also re-run the free demos -> demos.json
```

`--demos` uses no API calls. It replays `recordings/fix.jsonl` through Cato's real screen, headless mode, the cost limit, and Ctrl+C at the permission question. It also runs Cato v0.2's Ctrl+C for comparison, the generator example, the bytes `rich` sends to the terminal, and the map of which file calls which. It works in `/tmp/shop`, so the screen looks exactly like the one in the video. It uses the Part 1 and Part 2 folders next to this one for the comparisons. Two things will differ a little from the recording: how long each run took, and how many spinner frames fit in a quarter of a second.

To record your own live runs, set `OPENROUTER_API_KEY` and run `python record_part3.py --live` (about 5 cents). Your numbers will differ a little, because the model's answers and the network vary from run to run.

## Test it without a model

```bash
pip install pytest
python -m pytest -q tests        # a fake model streams scripted answers: no API calls, no cost
```

## What each file does

| File | What it is | In the video |
|---|---|---|
| [`cato/model.py`](cato/model.py) | One streamed request to the model through OpenRouter: the pieces as they arrive, tool calls glued back together, and record and replay | 06:46 one flag: stream · 10:19 `live_pieces` · 11:48 `glue_tool_call` · 12:23 `stream_model` · 13:06 one complete reply · 39:00 record once, replay for free |
| [`cato/agent.py`](cato/agent.py) | The loop from Part 1, now a generator that hands out events, plus `repair` and the cost limit | 15:09 five events · 18:35 `run_agent` · 19:10 every print became a yield · 34:45 `repair` · 36:24 the cost limit |
| [`cato/ui.py`](cato/ui.py) | The screen: the `Screen` class, asking permission, tool summaries, the status line, slash commands and Ctrl+C | 14:16 one loop, many listeners · 19:56 the screen just listens · 29:13 `Screen` · 29:49 `stop` · 30:12 `show_tool_end` · 30:44 asking you first · 31:13 the status line · 31:44 slash commands · 35:14 catch it, repair, keep going |
| [`cato/__main__.py`](cato/__main__.py) | The `cato` command, and headless mode (`-p`) | 20:35 a listener with no screen · 42:58 run it yourself |
| [`cato/tools.py`](cato/tools.py) | The six tools from Part 2, unchanged | 03:10 Cato's files |
| [`shop/`](shop/) | The tiny shop with the bug from Parts 1 and 2 (the cart ignores how many you bought) | 37:26 the fix |
| [`runs.json`](runs.json) | The frozen recording of the live runs (Claude Sonnet 5.5): v0.3's streamed answer, the same question sent without streaming, v0.2's screen, the fix, and a chat with an unanswered tool request | 00:00 cold open · 07:30 the first piece and the last · 17:50 where the time goes · 33:51 every tool request needs an answer · 37:26 the fix |
| [`recordings/`](recordings/) | The two sessions saved with `--record`, ready to replay | 39:00 record once, replay for free |
| [`demos.json`](demos.json) | Everything else on the slides, from Cato's real code: the replay, headless JSON, the cost limit, both Ctrl+C screens, the slash commands, the terminal bytes and the file map | 03:10 Cato's files · 09:27 generators · 21:14 `cato -p` as JSON · 24:51 the spinner · 26:35 go back, erase, draw again · 32:17 Ctrl+C ended everything · 32:52 where Ctrl+C goes |
| [`record_part3.py`](record_part3.py) | Records `runs.json` (with a key) and `demos.json` (free), and rebuilds `numbers.json` | throughout |
| [`tests/`](tests/) | Tests for the tools, streaming, events, Ctrl+C, headless mode and the screen, with a fake model | (behind the scenes) |

The live runs happened in `/tmp/shop` (macOS shows it as `/private/tmp/shop`), so no output was edited.
