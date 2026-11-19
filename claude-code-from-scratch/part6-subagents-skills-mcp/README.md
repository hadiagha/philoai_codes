# Part 6 · Subagents, Skills and MCP: the code

This is the code behind the PhiloAI video *Build a Claude Code Clone From Scratch, Part 6: Subagents, Skills and MCP*.

**Cato v0.6** learns to get help, in three ways, and each one arrives as one more tool on the same tool list:

- **Helpers (subagents).** The `Agent` tool runs the loop again with a fresh message list. The helper does its reading on a desk of its own, and only its final report comes back.
- **Recipe cards (skills).** A skill is a folder with a `SKILL.md`. Only a one-line menu sits on the desk; the `Skill` tool loads the full card when a task needs it. Slash commands are cards too, with `$ARGUMENTS` filled in.
- **A plug (MCP).** Cato starts another program, talks to it in numbered JSON-RPC messages over its input and output, and turns its tools into Cato tools named `mcp__<server>__<tool>`.

In the video, one broad question about Python's `asyncio` package grows the desk to 17,553 tokens when Cato searches by itself: 22 tool calls, 11 cents. With a helper, the main desk ends at 6,023 tokens, but the bill almost doubles to 21 cents, and the follow-up question needs 4 more reads. Then the add-product skill guides a real edit, `/review shop.py` sends the reviewer helper (one of its five findings has a wrong number, and the main loop passes it on), and a notes server saves a note through the same gate as every other tool.

Three files are new: `cards.py`, `helpers.py` and `mcp.py`. The loop, the model client and the whole gate from Part 4 are unchanged.

## Run Cato yourself

You need Python 3.10 or newer and an [OpenRouter](https://openrouter.ai) key.

```bash
pip install -e .                         # from this folder; adds the `cato` command
export OPENROUTER_API_KEY=sk-or-...

cp -r shop /tmp/my-shop && cd /tmp/my-shop   # work on a copy: Cato really edits files and runs commands
cato --model sonnet                          # asks before starting the notes server from .mcp.json
```

The shop comes with everything from the video:

| File | What it is |
|---|---|
| `.cato/agents/reviewer.md` | A helper card: a reviewer that may only read (`tools: Read, Glob, Grep`) |
| `.cato/skills/add-product/` | A skill: `SKILL.md` (how this team adds a product) and `check_prices.py`, a script the skill runs but never loads onto the desk |
| `.cato/commands/review.md` | A command: `/review <file>` sends the reviewer helper |
| `.mcp.json` and `mcp/notes_server.py` | An MCP server with two tools, `add_note` and `list_notes`, in about 60 lines of plain Python |
| `CATO.md`, `.cato/settings.json`, `.cato/hooks/` | The notes, rules and hooks from Parts 4 and 5 |

The `.env` in the shop is fake (`not-a-real-key-123`).

On the screen, try:

- `/agents` to see the helpers Cato can send: the two built-in ones (`explore`, which only reads, and `general`) plus your own cards
- `/skills` to see the menu the model sees
- `/review shop.py` for a command that sends a helper
- `/mcp` to see the servers from `.mcp.json` and their tools
- "Add a product called cocoa, for $4.25." to watch the model load the skill and follow it
- "Save a note for me: order more coffee beans on Friday." to call the notes server (the gate asks first)

Your own cards for every project go in `~/.cato/agents/`, `~/.cato/skills/` and `~/.cato/commands/`. A project card wins over yours with the same name.

## Watch a recorded session, with no API key

The `recordings/` folder holds the nine real sessions from the video. Replaying one needs no key and costs nothing. Cato's real tools, gate and MCP server still run. The sessions used the full path `/tmp/shop`, so replay them there:

```bash
REC="$PWD/recordings"                        # from this folder
cp -r shop /tmp/shop && cd /tmp/shop         # /tmp/shop must not exist yet
cato -p 'Add a product called cocoa, for $4.25.' --replay "$REC/skill.jsonl" --yes --json --verbose
python test_shop.py                          # all passed: cocoa is in PRICES, at 425 cents
```

The notes session, in a fresh copy of the shop:

```bash
rm -rf /tmp/shop && cp -r shop /tmp/shop && cd /tmp/shop     # from this folder
cato -p 'Save a note for me: order more coffee beans on Friday.' --replay "$REC/notes.jsonl" --yes --json
cat notes.json                               # the note the server saved
```

`--yes` says yes when Cato asks, and starts the MCP servers in headless mode. Deny rules and hooks still win.

## Check the numbers, with no API key

`runs.json` is the frozen recording of the live runs in the video, with every request (the main loop's and each helper's), its token counts, its cost and the exact screen. `demos.json` holds everything else on the slides. This rebuilds every number on the slides from those two files, for free:

```bash
pip install -r requirements.txt
python record_part6.py              # -> numbers.json
python record_part6.py --demos      # also re-run the free demos -> demos.json
```

`--demos` uses no API calls. It records every line Cato and an MCP server send each other, for the current protocol and for an older server that needs the handshake (`legacy_server.py`); reads the cards as files and as Cato sees them; measures what each piece puts on the desk (the tool forms, the skill menu, a full card); draws the map of which file calls which, for Parts 5 and 6; and replays every recording through Cato's real screen. It uses the Part 5 folder next to this one for the file map. Run there, it reproduces `demos.json` exactly.

It writes to `/tmp/shop` and `/tmp/proj` (a copy of your Python's `asyncio` package) and refuses to touch them if it didn't make them.

To record your own live runs, set `OPENROUTER_API_KEY` and run `python record_part6.py --live` (about 70 cents; `--only=alone,helper` runs just some of them). Your numbers will differ, because the model's choices vary from run to run, and because the video used Python 3.14's `asyncio`. Each run in the video happened once, so run your own tasks more than once before you decide.

## Test it without a model

```bash
pip install pytest
python -m pytest -q tests        # a fake model gives scripted answers: no API calls, no cost
```

## What each file does

| File | What it is | In the video |
|---|---|---|
| [`cato/cards.py`](cato/cards.py) | New. Reads a card (a small header, then the body), finds every card of one kind, builds the skill menu, and fills in `$ARGUMENTS` | 08:42 a helper is a card · 09:21 read_card · 09:49 find_cards · 21:28 a skill is a folder · 22:11 skill_menu · 25:24 a command · 26:05 fill |
| [`cato/helpers.py`](cato/helpers.py) | New. The two built-in helpers, `run_helper` (the same loop with a fresh list), which tools a helper may use, and the `Agent` and `Skill` tools | 10:17 the built-in helpers · 10:43 run_helper · 11:54 helper_tools · 12:24 the Agent record · 22:55 the Skill tool |
| [`cato/mcp.py`](cato/mcp.py) | New. Starts a server, sends numbered requests and matches the answers, asks which version it speaks (the handshake for older servers), turns its tools into Cato tools, and stops it | 31:37 numbered questions, numbered answers · 33:02 every request says its version · 33:58 send, read_message · 34:25 request · 34:48 start_server · 35:18 tool_caller · 35:40 server_tools · 36:12 load_servers · 36:41 stop_servers |
| [`cato/context.py`](cato/context.py) | The desk from Part 5, with the skill menu added to the reminder in your first message | 22:31 reminders |
| [`cato/ui.py`](cato/ui.py) | The screen: `/agents`, `/skills`, `/mcp`, your own commands, and a helper's steps shown under its call | 13:37 what the screen shows · 26:31 /review, for real · 37:40 save a note, for real |
| [`cato/__main__.py`](cato/__main__.py) | The `cato` command, now with the helpers and MCP servers in headless mode too | 45:45 run it yourself |
| [`cato/tools.py`](cato/tools.py) | The six tools; the form check now skips types it doesn't know, for forms from outside tools | 42:18 the package, file by file |
| [`cato/agent.py`](cato/agent.py), [`cato/model.py`](cato/model.py), [`cato/permissions.py`](cato/permissions.py), [`cato/hooks.py`](cato/hooks.py), [`cato/settings.py`](cato/settings.py) | The loop, the model client and the gate, unchanged | 42:18 the package, file by file |
| [`shop/`](shop/) | The tiny shop, with a helper card, a skill, a command and the notes server | 23:24 add cocoa, for real · 26:31 /review · 37:40 save a note |
| [`runs.json`](runs.json) | The frozen recording of the live runs (Claude Sonnet 5.5): the asyncio question alone, with a helper, and with the first helper card; a tiny question both ways; the skill, a question it doesn't match, `/review`, and the notes server | 00:00 cold open · 12:42 alone, or with a helper · 14:01 only the report comes back · 14:54 where the money went · 15:45 the follow-up · 16:24 a tiny job · 23:24 add cocoa · 24:09 the card stays in its file · 26:31 /review · 37:40 save a note |
| [`recordings/`](recordings/) | The nine sessions saved with `--record`, ready to replay | 23:24 add cocoa · 37:40 save a note |
| [`demos.json`](demos.json) | Everything else on the slides, from Cato's real code: the MCP wire, the cards, what each piece puts on the desk, and the file map | 03:37 Cato's files · 32:12 the whole conversation · 33:02 every request says its version · 38:25 every plug puts forms on the desk |
| [`legacy_server.py`](legacy_server.py) | A tiny older MCP server that wants the handshake first, for the wire demo | 33:02 every request says its version |
| [`record_part6.py`](record_part6.py) | Records `runs.json` (with a key) and `demos.json` (free), and rebuilds `numbers.json` | throughout |
| [`tests/`](tests/) | Tests for the tools, streaming, the gate, the desk, and the new cards, helpers, skills, commands and MCP, with a fake model and the real notes server | (behind the scenes) |

The live runs happened in `/tmp/shop` and `/tmp/proj` (macOS shows them as `/private/tmp/...`), so no original files were edited.
