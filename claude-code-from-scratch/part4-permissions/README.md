# Part 4 · Permissions and Hooks: the code

This is the code behind the PhiloAI video *Build a Claude Code Clone From Scratch, Part 4: Permissions and Hooks*.

**Cato v0.4** gets a gate. Every tool call stops at `check_call()` before it runs. The gate cuts a shell command into pieces, checks each piece against your rules (allow, ask or deny, where deny always wins), and runs your own scripts, called hooks, before and after a tool. Four modes change what's allowed by default, including plan mode, where Cato can only look. Read-only tools now run side by side.

In the video, a naive rule (`command.startswith("ls")`) says yes to `ls && rm -rf build`, and the build folder really disappears. Then Cato v0.4 gets the same request from a real model. The gate refuses the `rm`, and the model says it won't try another way. Then v0.4 fixes the shop's bug from Parts 1 to 3: 5 calls, 11.3 seconds and $0.0401. All 4 tests pass, the build folder stays, and `.env` stays closed.

Three files are new: `permissions.py`, `hooks.py` and `settings.py`. The six tools in `cato/tools.py` and the model client in `cato/model.py` are the same as in Part 3.

## Run Cato yourself

You need Python 3.10 or newer and an [OpenRouter](https://openrouter.ai) key.

```bash
pip install -e .                         # from this folder; adds the `cato` command
export OPENROUTER_API_KEY=sk-or-...

cp -r shop /tmp/my-shop && cd /tmp/my-shop   # work on a copy: Cato really edits files and runs commands
python test_shop.py                          # 2 failed: the bug is real
cato --model sonnet                          # then type: The tests fail. Make them pass. Then delete the build folder, and show me what's in .env.
```

The shop comes with its rules in `.cato/settings.json` and both hooks in `.cato/hooks/`:

- **allow:** `Bash(python3 test_shop.py)`, `Bash(ls *)`, `Bash(cat *)`, `Bash(git status)`
- **ask:** `Bash(git push *)`
- **deny:** `Bash(rm *)`, `Read(.env)`, `Edit(.env)`, `Write(.env)`
- **hooks:** `protect_files.py` runs before every Edit and Write and stops changes to `.env` and the tests. `check_python.py` runs after them and sends any syntax error back to the model.

The `.env` in the shop is fake (`not-a-real-key-123`). It's there so you can watch the deny rule work.

Then try the rest of what the video shows:

```bash
cato --mode plan                             # look, don't touch: Cato explores and writes a plan
cato -p "Explain this project" --json        # headless, as in Part 3
```

On the screen, type `/permissions` to see the rules in use, and press Shift+Tab to switch to the next mode. When Cato asks, answer `1` (yes), `2` (yes, and don't ask again) or `3` (no).

## Watch the recorded fix, with no API key

`recordings/fix.jsonl` is the real session from the video. Replaying it needs no key and costs nothing. Cato's real gate and tools still run, so it really fixes the shop, and it really can't delete the build folder or read `.env`. The model used the full path `/tmp/shop`, so replay it there:

```bash
REC="$PWD/recordings/fix.jsonl"              # from this folder
cp -r shop /tmp/shop && cd /tmp/shop         # /tmp/shop must not exist yet
cato -p "The tests fail. Make them pass. Then delete the build folder, and show me what's in .env." --replay "$REC" --yes --json
python test_shop.py                          # all passed, and build/ is still there
```

`--yes` says yes when Cato asks. Deny rules and hooks still win.

## Check the numbers, with no API key

`runs.json` is the frozen recording of the three live runs in the video, with every call, its cost and the exact screen. `demos.json` holds everything else on the slides. This rebuilds every number on the slides from those two files, for free:

```bash
pip install -r requirements.txt
python record_part4.py              # -> numbers.json
python record_part4.py --demos      # also re-run the free demos -> demos.json
python record_part4.py --layers     # also re-run the seven bad calls against each layer
```

`--demos` uses no API calls. It runs the naive rule for real on a throwaway copy of the shop, then `split_command`, the rule matching and `decide` on real examples in all four modes, "don't ask again", both hooks on real tool calls, the same delete inside a macOS sandbox, reads one by one and side by side, the thread pool demo, and the map of which file calls which. It also replays all three recordings through Cato's real screen. It uses the Part 3 folder next to this one for the file map. Two things will differ a little from the recording: the timings, and the dates that `ls -la` prints.

`--layers` tests each layer on its own against seven bad calls (three deletes, two reads of `.env`, and two ways to change a test's expected value). For each call it runs the hook, the rules, and, for shell commands, macOS `sandbox-exec` with a profile that locks `build/` and `.env`. Then it checks what really happened. Every layer misses something, and one call (`sed` on the test file) gets all the way to you. The sandbox part needs macOS.

Both write to `/tmp/shop` and refuse to touch it if they didn't make it.

To record your own live runs, set `OPENROUTER_API_KEY` and run `python record_part4.py --live` (about 8 cents). Your numbers will differ a little, because the model's answers and the network vary from run to run.

## Test it without a model

```bash
pip install pytest
python -m pytest -q tests        # a fake model gives scripted answers: no API calls, no cost
```

## What each file does

| File | What it is | In the video |
|---|---|---|
| [`cato/permissions.py`](cato/permissions.py) | The gate: rule matching, cutting a command into pieces, the eight checks in order, "don't ask again", and `check_call` | 12:47 a rule, up close · 13:52 `matches` · 14:38 one line, several commands · 16:13 quotes first · 16:50 then the joints · 17:21 two helpers · 17:53 eight checks · 19:11 `decide` · 21:24 don't ask again · 21:59 `check_call` |
| [`cato/settings.py`](cato/settings.py) | Reads the rules from `~/.cato/settings.json` and the project's `.cato/settings.json`, and joins them into one dict | 11:24 where the rules live · 12:04 two files, one dict |
| [`cato/hooks.py`](cato/hooks.py) | Finds the hooks for a tool, runs them with JSON on stdin, and reads the exit code | 24:22 JSON in, an exit code out · 26:34 which hook, for which tool · 27:15 run them, read the exit code |
| [`cato/agent.py`](cato/agent.py) | The loop from Part 3, now asking the gate before every tool, running the after-hooks, and running reads side by side | 22:49 where the loop calls it · 27:51 the inspector, after the tool · 35:41 only reads share a group · 36:22 run, then answer in order |
| [`cato/ui.py`](cato/ui.py) | The screen: the three-choice question, the mode in the status line, `/permissions` and Shift+Tab | 10:28 four modes · 20:27 yes, yes and don't ask again, or no |
| [`cato/__main__.py`](cato/__main__.py) | The `cato` command, now with `--mode` | 43:21 run it yourself |
| [`cato/tools.py`](cato/tools.py), [`cato/model.py`](cato/model.py) | The six tools and the streaming model client from Part 3, unchanged | 03:40 Cato's files |
| [`shop/`](shop/) | The tiny shop with the bug from Parts 1 to 3, a build folder, a fake `.env`, the rules and both hooks | 25:03 hook 1: hands off · 25:47 hook 2: does it still compile? · 37:03 the fix |
| [`runs.json`](runs.json) | The frozen recording of the live runs (Claude Sonnet 5.5): the cold open's request, the fix, and plan mode | 00:00 cold open · 37:03 fix it, delete it, show me · 38:19 look, don't touch |
| [`recordings/`](recordings/) | The three sessions saved with `--record`, ready to replay | 37:03 the fix |
| [`demos.json`](demos.json) | Everything else on the slides, from Cato's real code: the naive rule, the rule decisions, both hooks, the sandbox, the seven bad calls, the timings, who wrote the model's input, and the file map | 00:00 the first rule everyone writes · 03:40 Cato's files · 07:21 who writes what the model reads · 31:14 lock the build folder · 32:40 every layer has holes · 34:14 reads side by side |
| [`threads_demo.py`](threads_demo.py) | Four jobs that each wait 0.3 seconds, run side by side with a thread pool | 35:06 a pool of helpers |
| [`record_part4.py`](record_part4.py) | Records `runs.json` (with a key) and `demos.json` (free), and rebuilds `numbers.json` | throughout |
| [`tests/`](tests/) | Tests for the tools, streaming, the rules, the modes, hooks and reads side by side, with a fake model | (behind the scenes) |

The live runs happened in `/tmp/shop` (macOS shows it as `/private/tmp/shop`), so no output was edited.
