"""The desk: everything the AI sees on each call, and how Cato keeps it from overflowing.

On the desk, in order:
    1. the system prompt  - the same all session, so it can be cached (the reread discount)
    2. reminders          - CATO.md files, slipped into your first message
    3. the conversation   - your messages, its replies, tool calls and their results

Clearing the desk, cheapest step first:
    1. trim long output              (tools.trim, since Part 2)
    2. save big output to a file     (tools.trim, from Part 5)
    3. clear old tool results        (clear_old_results)
    4. summarize everything          (summarize)
"""
import json
import os
import platform
import subprocess
from datetime import date
from pathlib import Path

from .model import stream_model

DESK_LIMIT = 200_000      # tokens. Cato clears the desk when it gets this full.
KEEP_RESULTS = 3          # the newest tool results are never cleared (the Claude API keeps 3 too)
CLEARED = "[Old tool result cleared to save space. Run the tool again if you need it.]"


# ---------------------------------------------------------------- 1. the system prompt

INSTRUCTIONS = """You are Cato, a coding assistant working in a terminal.

# How to work
- Use Glob and Grep to find code, Read to look at it, and Edit to change it.
- Read a file before you edit it. Make the smallest change that solves the task.
- Use Bash to run tests, git and other commands.
- When the task is done, reply with a short summary.

# Safety
- If a tool call is not allowed, don't try to get around it; ask the user.
- Never delete files or push code unless the user asked for it.

# Memory
- Project instructions from CATO.md files arrive inside <system-reminder> tags. Follow them.
- When the user asks you to remember something, add it as a short line to ./CATO.md."""


def environment():
    """Facts about where Cato runs. They don't change during a session."""
    try:
        branch = subprocess.run(["git", "branch", "--show-current"], capture_output=True,
                                text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        branch = ""
    return (f"<env>\nWorking folder: {os.getcwd()}\nPlatform: {platform.system()}\n"
            f"Date: {date.today().isoformat()}\nGit branch: {branch or '(not a git repo)'}\n</env>")


def system_prompt():
    """Unchanging parts first, so the start of every request is identical (and cheap)."""
    return INSTRUCTIONS + "\n\n" + environment()


# ---------------------------------------------------------------- 2. CATO.md, the note on the fridge

def memory_files():
    """Your ~/.cato/CATO.md, then CATO.md in every folder from the top down to here."""
    found = [Path.home() / ".cato" / "CATO.md"]
    folders = [Path.cwd(), *Path.cwd().parents]
    found += [folder / "CATO.md" for folder in reversed(folders)]
    return [path for path in dict.fromkeys(found) if path.is_file()]


def reminders():
    """The text slipped into the first message: every CATO.md file, with where it came from."""
    parts = [f"Contents of {path}:\n\n{path.read_text().strip()}" for path in memory_files()]
    if not parts:
        return ""
    return ("<system-reminder>\nInstructions from CATO.md files. They override the defaults.\n\n"
            + "\n\n".join(parts) + "\n</system-reminder>")


def with_reminders(text, first):
    """Your message, with the reminders in front if this is the first one."""
    note = reminders() if first else ""
    return f"{note}\n\n{text}" if note else text


# ---------------------------------------------------------------- measuring the desk

def estimate_tokens(value):
    """About 4 characters per token. Good enough to see what fills the desk."""
    return len(value if isinstance(value, str) else json.dumps(value)) // 4


def desk_breakdown(messages, schemas):
    """How many tokens each kind of thing takes, for /context."""
    parts = {"system prompt": estimate_tokens(messages[0]["content"]) if messages else 0,
             "tool forms": estimate_tokens(schemas), "CATO.md": estimate_tokens(reminders()),
             "your messages": 0, "replies and tool calls": 0, "tool results": 0}
    for message in messages[1:]:
        size = estimate_tokens(message.get("content") or "") + estimate_tokens(message.get("tool_calls") or "")
        key = {"user": "your messages", "tool": "tool results"}.get(message["role"], "replies and tool calls")
        parts[key] += size
    parts["your messages"] = max(0, parts["your messages"] - parts["CATO.md"])
    return parts


# ---------------------------------------------------------------- 3. clearing old results

def clear_old_results(messages, keep=KEEP_RESULTS):
    """Replace the content of old tool results with a short note. The pairs stay together."""
    results = [m for m in messages if m["role"] == "tool"]
    cleared = 0
    for message in results[:-keep] if keep else results:
        if len(message["content"]) > len(CLEARED):
            message["content"] = CLEARED
            cleared += 1
    return cleared


def pairs_ok(messages):
    """The pairing rule: every tool request has exactly one answer, right after it."""
    waiting = set()
    for message in messages:
        if message["role"] == "tool":
            if message.get("tool_call_id") not in waiting:
                return False
            waiting.remove(message["tool_call_id"])
        else:
            if waiting:
                return False
            waiting = {call["id"] for call in message.get("tool_calls") or []}
    return not waiting


# ---------------------------------------------------------------- 4. summarizing

SUMMARY_REQUEST = """Stop here, and don't call any tools. Summarize this coding session so the work
can continue from the summary alone. Include: the user's goal and requests, decisions made,
files read or changed (with paths), what was tried and what failed, the current state,
and the next steps. Be brief and specific."""


def recent_files(messages, limit=3):
    """Files the model touched most recently, newest first."""
    paths = []
    for message in reversed(messages):
        for call in reversed(message.get("tool_calls") or []):
            try:
                path = json.loads(call["function"]["arguments"]).get("file_path")
            except (json.JSONDecodeError, AttributeError):
                path = None
            if path and path not in paths and Path(path).is_file():
                paths.append(path)
    return paths[:limit]


def summarize(messages, model, schemas=()):
    """Swap the whole conversation for a summary note, plus the files it was working on.

    The summary request is the chat itself with one more question at the end. So it starts
    exactly like the last request, and the model rereads all of it at the discount.
    Returns the usage of the summary call, so its cost is counted too.
    """
    request = messages + [{"role": "user", "content": SUMMARY_REQUEST}]
    for piece in stream_model(request, list(schemas), model):
        if piece[0] == "reply":
            summary, usage = piece[1]["content"] or "", piece[2]
    files = []
    for path in recent_files(messages):
        text = Path(path).read_text(errors="replace")
        if len(text) < 12_000:
            files.append(f"Current contents of {path}:\n{text}")
    note = ("This conversation continues an earlier one that was summarized to save space.\n\n"
            f"Summary:\n{summary}")
    if files:
        note += "\n\n" + "\n\n".join(files)
    note += "\n\nContinue the work from where it stopped."
    messages[1:] = [{"role": "user", "content": with_reminders(note, first=True)}]
    return usage
