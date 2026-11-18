# Part 5 · Memory and Context: the code

This is the code behind the PhiloAI video *Build a Claude Code Clone From Scratch, Part 5: Memory and Context*.

**Cato v0.5** learns to manage what the model sees. Every request carries the whole chat, so Cato now measures that desk (`/context`), keeps the start of every request the same so the provider can reread it at a discount, reads your notes from `CATO.md` files folder by folder, and clears the desk in steps, cheapest first, when it gets full: trim long output, save big output to a file, clear old tool results, and finally summarize.

In the video, one question about Python's own `email` package takes 10 requests. The desk grows from about 1,700 tokens to almost 22,000, and the model reads 136,838 tokens in all. At the full price that's $0.33. Cato paid **$0.12**, because 84% was reread from the cache. Then a note in `~/.cato/CATO.md` ("every code change gets one line in CHANGELOG.md") is ignored by v0.4 and followed by v0.5. Then `/compact` swaps a long chat for one summary note, and a desk that's too small makes Cato read the same files again and again: 14 requests instead of 10, and $0.20 instead of $0.12.

One file is new: `context.py`. The gate from Part 4 (`permissions.py`, `hooks.py`, `settings.py`) is unchanged.

## Run Cato yourself

You need Python 3.10 or newer and an [OpenRouter](https://openrouter.ai) key.

```bash
pip install -e .                         # from this folder; adds the `cato` command
export OPENROUTER_API_KEY=sk-or-...

cp -r shop /tmp/my-shop && cd /tmp/my-shop   # work on a copy: Cato really edits files and runs commands
cato --model sonnet                          # reads every CATO.md from the top folder down
```

The shop comes with its notes in `CATO.md`, its rules in `.cato/settings.json` and both hooks from Part 4 in `.cato/hooks/`. The `.env` in the shop is fake (`not-a-real-key-123`).

On the screen, try:

- `/context` to see what's on the desk, as a colored bar, one color per kind of thing
- `/compact` to swap the chat for a summary note, plus the files it was working on
- `/memory` to see which `CATO.md` files Cato read
- "Please remember this for next time: …" to make Cato add a line to `CATO.md` (it's an edit, so the gate asks you first)

The status line shows how much of each request came from the cache. To watch the desk fill up and get cleared, start Cato with a small desk:

```bash
cato --desk-limit 10000                      # the default is 200,000 tokens
```

Your own notes for every project go in `~/.cato/CATO.md`.

## Watch a recorded session, with no API key

The `recordings/` folder holds the six real sessions from the video. Replaying one needs no key and costs nothing. Cato's real tools and gate still run. The tea task from the video used the full path `/tmp/shop`, so replay it there:

```bash
REC="$PWD/recordings/rules_v05.jsonl"        # from this folder
cp -r shop /tmp/shop && cd /tmp/shop         # /tmp/shop must not exist yet
cato -p 'Add a product called tea, for $3.50. Then run the tests.' --replay "$REC" --yes --json
cat CHANGELOG.md                             # the line v0.5 wrote, because the note asked for it
python test_shop.py                          # all passed
```

`--yes` says yes when Cato asks. Deny rules and hooks still win.

## Check the numbers, with no API key

`runs.json` is the frozen recording of the live runs in the video, with every request, its token counts, its cost and the exact screen. `demos.json` holds everything else on the slides. This rebuilds every number on the slides from those two files, for free:

```bash
pip install -r requirements.txt
python record_part5.py              # -> numbers.json
python record_part5.py --demos      # also re-run the free demos -> demos.json
```

`--demos` uses no API calls. It measures the first page (the system prompt, the tool forms and the notes), walks a real folder tree for `CATO.md` files, prints a big file and saves it to `.cato/outputs`, clears old results on the recorded email session, checks the pairing rule, compares "4 characters per token" with the API's real counts, draws the map of which file calls which, and replays every recording through Cato's real screen. It uses the Part 4 folder next to this one for the v0.4 comparison and the file map. A few things will differ a little from the recording: the date in the first page, the name of the saved output file, and test timings.

It writes to `/tmp/shop` and `/tmp/mail` (a copy of Python's `email` package) and refuses to touch them if it didn't make them.

To record your own live runs, set `OPENROUTER_API_KEY` and run `python record_part5.py --live` (about 55 cents; `--only=long,cache` runs just some of them). Your numbers will differ a little, because the model's answers, the network and the cache vary from run to run.

## Test it without a model

```bash
pip install pytest
python -m pytest -q tests        # a fake model gives scripted answers: no API calls, no cost
```

## What each file does

| File | What it is | In the video |
|---|---|---|
| [`cato/context.py`](cato/context.py) | New. Everything about the desk: the rough token count and the split by kind, the first page (instructions plus the environment), the `CATO.md` walk and the reminder, clearing old results, the pairing check, and the summary | 08:58 count the desk, by kind · 11:00 the first page, in code · 12:56 find the notes, and join them · 13:30 why the notes ride in your first message · 22:56 swap it, never delete it · 24:13 check the pairs · 24:53 ask for a summary · 25:31 swap the chat for one note |
| [`cato/agent.py`](cato/agent.py) | The loop from Part 4, now clearing the desk when it's full: it tries clearing old results on a copy first, and summarizes only if that's not enough | 26:37 where the loop clears the desk · 28:19 a desk that's too small |
| [`cato/model.py`](cato/model.py) | The model client from Part 3, with one new flag: `cache_control` for Claude models, so the start of each request is reread at a discount | 18:27 the discount is one flag |
| [`cato/tools.py`](cato/tools.py) | The six tools, now saving big output to a file and giving the model a short version plus the path | 21:21 big output · 21:52 trim, and keep a copy |
| [`cato/ui.py`](cato/ui.py) | The screen: `/context`, `/compact`, `/memory`, the notes in your first message, and the cache in the status line | 09:37 /context: the desk as a bar · 27:30 /compact for real |
| [`cato/__main__.py`](cato/__main__.py) | The `cato` command, now with `--desk-limit` | 33:43 run it yourself |
| [`cato/permissions.py`](cato/permissions.py), [`cato/hooks.py`](cato/hooks.py), [`cato/settings.py`](cato/settings.py) | The gate from Part 4, unchanged | 29:51 what Part 5 added, and where |
| [`shop/`](shop/) | The tiny shop from Parts 1 to 4 (with Part 4's fix), its `CATO.md`, its rules and both hooks | 14:12 your own note, with and without it · 14:53 "please remember this" |
| [`runs.json`](runs.json) | The frozen recording of the live runs (Claude Sonnet 5.5): the email question, the small desk, the tea task for v0.4 and v0.5, `/compact`, "please remember", five tiny cache requests, and the pairing rule on two models | 00:00 cold open · 14:12 your own note · 16:38 five requests, one rule · 18:59 the desk, turn by turn · 23:23 a request and its answer stay together · 26:07 what the summary costs · 27:30 /compact · 28:19 thrashing |
| [`recordings/`](recordings/) | The six sessions saved with `--record`, ready to replay | 27:30 /compact for real |
| [`demos.json`](demos.json) | Everything else on the slides, from Cato's real code: the rough count against the real one, the first page, the folder walk, the big output, clearing, and the file map | 03:35 Cato's files · 07:25 a rough count, and a real one · 10:18 the first page · 12:14 found folder by folder · 22:21 clear the oldest results |
| [`record_part5.py`](record_part5.py) | Records `runs.json` (with a key) and `demos.json` (free), and rebuilds `numbers.json` | throughout |
| [`tests/`](tests/) | Tests for the tools, streaming, the gate and the desk (the `CATO.md` walk, clearing, the pairing rule, the summary), with a fake model | (behind the scenes) |

The live runs happened in `/tmp/shop` and `/tmp/mail` (macOS shows them as `/private/tmp/...`), so no output was edited.
