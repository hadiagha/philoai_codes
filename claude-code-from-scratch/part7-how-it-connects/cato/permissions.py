"""The traffic light: should a tool call go ahead (allow), ask you first (ask), or never run (deny)?

The checks always run in the same order:
    1. hooks        your scripts can stop anything
    2. deny rules   "never" always wins
    3. ask rules    "always ask me about this"
    4. the mode     plan mode only reads; bypass mode allows the rest
    5. reading inside the project is fine
    6. accept-edits mode allows edits inside the project
    7. allow rules  every piece of the command must be allowed
    8. otherwise    ask
"""
import fnmatch
import json
from pathlib import Path

from .hooks import run_hooks

MODES = ["default", "acceptEdits", "plan", "bypassPermissions"]
EDIT_TOOLS = {"Edit", "Write"}


def split_command(command):
    """Split 'ls && rm -rf build' into ['ls', 'rm -rf build'], so every piece gets checked.

    It splits on ; && || | & and new lines, but not inside quotes or in redirects like 2>&1.
    """
    pieces, current, quote, i = [], "", None, 0
    while i < len(command):
        ch = command[i]
        if ch == "\\" and quote != "'":
            current += command[i:i + 2]
            i += 2
            continue
        if quote:
            if ch == quote:
                quote = None
            current += ch
        elif ch in "'\"":
            quote = ch
            current += ch
        elif command.startswith(("&&", "||"), i):
            pieces.append(current)
            current = ""
            i += 1
        elif ch in ";|\n" or (ch == "&" and not current.endswith((">", "<"))
                              and command[i + 1:i + 2] != ">"):
            pieces.append(current)
            current = ""
        else:
            current += ch
        i += 1
    pieces.append(current)
    return [piece.strip() for piece in pieces if piece.strip()]


def hides_a_command(piece):
    """$(...) and backticks run another command inside this one. No rule can approve that."""
    return "$(" in piece or "`" in piece or "<(" in piece


def inside_project(path_text):
    path = Path(path_text or ".").expanduser()
    path = (path if path.is_absolute() else Path.cwd() / path).resolve()
    return path == Path.cwd().resolve() or Path.cwd().resolve() in path.parents


def targets(name, args):
    """What the rules look at: each piece of a command, or the file path."""
    if name == "Bash":
        return split_command(args.get("command", "")) or [""]
    if "file_path" in args or "path" in args:
        return [args.get("file_path") or args.get("path") or "."]
    return [""]


def matches(rule, name, target):
    """Does a rule like 'Bash(git *)', 'Read(.env)' or 'Glob' cover this call?"""
    rule_name, _, pattern = rule.partition("(")
    if not fnmatch.fnmatchcase(name, rule_name):
        return False
    if not pattern:
        return True                       # 'Read' alone covers every Read
    pattern = pattern[:-1]                # drop the closing ')'
    if name == "Bash":
        # 'git *' covers 'git status' and also plain 'git'
        return fnmatch.fnmatchcase(target, pattern) or (
            pattern.endswith(" *") and target == pattern[:-2])
    if "/" not in pattern:                # '.env' covers a file with that name in any folder
        return fnmatch.fnmatchcase(Path(target).name, pattern)
    relative = Path(target).as_posix().removeprefix("./")
    return fnmatch.fnmatchcase(relative, pattern)


def decide(name, args, tool, settings):
    """The traffic light for one tool call. Returns ("allow" | "ask" | "deny", why)."""
    pieces = targets(name, args)
    for rule in settings["deny"]:
        if any(matches(rule, name, piece) for piece in pieces):
            return "deny", f"the rule {rule} says never"
    for rule in settings["ask"]:
        if any(matches(rule, name, piece) for piece in pieces):
            return "ask", f"the rule {rule} says ask"

    mode = settings["mode"]
    if mode == "plan" and not tool.read_only:
        return "deny", "plan mode is on: only read and explore, then describe your plan"
    if mode == "bypassPermissions":
        return "allow", "bypass mode"
    if tool.read_only and name != "Bash" and inside_project(pieces[0]):
        return "allow", "reading inside the project"
    if mode == "acceptEdits" and name in EDIT_TOOLS and inside_project(pieces[0]):
        return "allow", "accept-edits mode"

    if name == "Bash" and any(hides_a_command(piece) for piece in pieces):
        return "ask", "the command runs another command inside it"
    if all(any(matches(rule, name, piece) for rule in settings["allow"]) for piece in pieces):
        return "allow", "allowed by your rules"
    return "ask", "no rule allows it yet"


def allow_from_now_on(settings, name, args):
    """The 'yes, and don't ask again' answer, for the rest of this session."""
    if name in EDIT_TOOLS:
        settings["mode"] = "acceptEdits"
    elif name == "Bash":
        settings["allow"] += [f"Bash({piece})" for piece in split_command(args.get("command", ""))]
    else:
        settings["allow"].append(name)


def check_call(name, arguments, tool, settings, ask):
    """Hooks, then the rules, then maybe you. Returns (allowed, message for the model if not)."""
    try:
        args = json.loads(arguments or "{}")
    except json.JSONDecodeError:
        return True, ""                   # run_tool will tell the model the JSON is broken
    if tool is None or not isinstance(args, dict):
        return True, ""                   # run_tool will answer "no such tool"
    stopped, message = run_hooks(settings, "PreToolUse", name, args)
    if stopped:
        return False, f"A hook stopped this: {message}"
    decision, why = decide(name, args, tool, settings)
    if decision == "deny":
        return False, f"Not allowed: {why}. Don't try to get around this."
    if decision == "ask":
        answer = ask(name, arguments, why) if ask else "no"
        if answer == "always":
            allow_from_now_on(settings, name, args)
        elif answer != "yes":
            return False, "The user said no. Ask them what to do instead."
    return True, ""
