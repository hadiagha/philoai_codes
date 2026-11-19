"""The screen: an input box, streamed answers, tool lines, diffs and a status line.

The loop never prints. It hands out events, and this file decides how each one looks.
"""
import json
import os
from pathlib import Path

import httpx
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel
from rich.terminal_theme import TerminalTheme

from . import __version__
from .agent import describe, repair, run_agent
from .context import (DESK_LIMIT, desk_breakdown, memory_files, summarize,
                      system_prompt, with_reminders)
from .model import MODELS, ModelError
from .permissions import MODES
from .settings import load_settings
from .cards import fill, find_cards
from .helpers import all_helpers, helper_tools
from .mcp import load_servers, stop_servers
from .tools import TOOLS, tool_schemas

console = Console(highlight=False, record=True)

# PhiloAI colors, used when the screen is saved as an SVG for the slides.
PHILO_THEME = TerminalTheme(
    (13, 17, 23), (232, 237, 245),
    [(13, 17, 23), (255, 102, 112), (69, 232, 145), (255, 184, 72),
     (167, 201, 255), (255, 169, 207), (0, 223, 254), (169, 180, 198)],
    [(107, 119, 140), (255, 102, 112), (69, 232, 145), (255, 184, 72),
     (167, 201, 255), (255, 169, 207), (0, 223, 254), (232, 237, 245)],
)

HELP = """[bold]Commands[/]
  /help           this list
  /model \\[name]   show or switch the model: sonnet, opus, sol, terra, gemini
  /cost           tokens and dollars so far
  /mode [name]    show or switch: default, acceptEdits, plan, bypassPermissions
  /permissions    the allow, ask and deny rules in use
  /context        what is on the desk right now
  /compact        summarize the chat to clear the desk
  /memory         the CATO.md files Cato read
  /agents         the helpers Cato can send
  /skills         the skills on the menu
  /mcp            outside tools from .mcp.json
  /<name> [text]  run your command or skill from .cato/commands or .cato/skills
  /clear          start a fresh chat
  /exit           quit (or Ctrl+D)
[dim]Shift+Tab switches the mode. Ctrl+C stops Cato in the middle of an answer.[/]"""


class Screen:
    """What is showing while an answer comes in: a spinner, or the words so far."""

    def __init__(self):
        self.spinner = None
        self.live = None
        self.words = None    # the answer so far, while it streams in

    def spin(self, label="Thinking…"):
        self.stop()
        self.spinner = console.status(f"[cyan]{label}[/]", spinner="dots")
        self.spinner.start()

    def add_words(self, piece):
        if self.words is None:
            self.stop()
            self.words = ""
            if console.is_terminal:  # redraw the markdown as it grows
                self.live = Live(console=console, refresh_per_second=12, vertical_overflow="visible")
                self.live.start()
        self.words += piece
        if self.live:
            self.live.update(Markdown(self.words))

    def stop(self):
        if self.spinner:
            self.spinner.stop()
            self.spinner = None
        if self.words is not None:
            if self.live:
                self.live.stop()
                self.live = None
            else:            # no terminal (a demo or a pipe): print the answer once
                console.print(Markdown(self.words))
            self.words = None


# ---------------------------------------------------------------- reading what you type

def read_line(session, prompt_text):
    """Your next line: from the keyboard, or from --inputs when making a demo."""
    if session["inputs"] is not None:
        if not session["inputs"]:
            raise EOFError
        line = session["inputs"].pop(0)
        console.print(f"{prompt_text}{escape(line)}")
        return line
    return console.input(prompt_text)


def ask_permission(session, screen, name, arguments, why):
    """Called when the rules say "ask". Returns "yes", "always" or "no"."""
    screen.stop()
    try:
        args = json.loads(arguments)
    except json.JSONDecodeError:
        args = {}
    if name == "Bash":
        console.print(f"  [yellow]Cato wants to run[/] [bold]{escape(args.get('command', ''))}[/]")
    else:
        console.print(f"  [yellow]Cato wants to use[/] [bold]{escape(describe(name, arguments))}[/]")
    if name == "Edit":  # show the change before you decide
        for line in str(args.get("old_string", "")).splitlines()[:8]:
            console.print(f"    [red]- {escape(line)}[/]")
        for line in str(args.get("new_string", "")).splitlines()[:8]:
            console.print(f"    [green]+ {escape(line)}[/]")
    always = {"Bash": "don't ask again for this command",
              "Edit": "allow all edits this session",
              "Write": "allow all edits this session"}.get(name, f"don't ask again for {name}")
    console.print(f"  [dim]({escape(why)})[/]\n"
                  f"  [bold]1[/] Yes   [bold]2[/] Yes, and {always}   [bold]3[/] No")
    answer = read_line(session, "  > ").strip().lower()
    screen.spin("Running…")
    return {"1": "yes", "y": "yes", "yes": "yes", "2": "always", "a": "always"}.get(answer, "no")


# ---------------------------------------------------------------- showing events

def show_tool_start(event):
    console.print(f"[blue]●[/] [bold]{escape(describe(event['name'], event['arguments']))}[/]")


def show_tool_end(event):
    lines = event["output"].splitlines() or [""]
    if not event["ok"]:
        console.print(f"  [red]└ {escape(lines[0][:200])}[/]")
        return
    if event["name"] in ("Edit", "Write") and len(lines) > 1:
        console.print(f"  [dim]└ {escape(lines[0])}[/]")
        for line in lines[1:30]:
            if line.startswith(("+++", "---")):
                continue
            color = "green" if line.startswith("+") else "red" if line.startswith("-") else "dim"
            console.print(f"    [{color}]{escape(line)}[/]")
        return
    shown = "\n    ".join(escape(line[:150]) for line in lines[:3])
    more = f" [dim]… +{len(lines) - 3} lines[/]" if len(lines) > 3 else ""
    console.print(f"  [dim]└ {shown}[/]{more}")


def status_line(session):
    cache = f" · cache {session['cache']:.0%}" if session["cache"] else ""
    return (f"{session['model']} · {session['settings']['mode']} mode · "
            f"{session['tokens']:,} tokens on the desk{cache} · ${session['cost']:.4f} · /help")


def session_tools(session, ask=None, report=lambda event: None):
    """Cato's six tools, plus Agent and Skill, plus every MCP server's tools."""
    helpers = helper_tools(session["model"], session["settings"], ask, report)
    return TOOLS + helpers + session["mcp_tools"]


def approve_server(session, name, config):
    """A project's .mcp.json can start any program, so Cato asks before each one, like Claude Code."""
    command = " ".join([config["command"], *config.get("args", [])])
    console.print(f"  [yellow]Start the MCP server[/] [bold]{escape(name)}[/]? It runs: {escape(command)}\n"
                  f"  [bold]1[/] Yes   [bold]3[/] No")
    return read_line(session, "  > ").strip().lower() in ("1", "y", "yes")


def show_helper_event(session, screen, event):
    """A helper's steps, shown indented under its Agent line. Its cost counts too."""
    if event["type"] == "tool_start":
        screen.stop()
        console.print(f"    [dim]└ {escape(describe(event['name'], event['arguments']))}[/]")
        screen.spin("Helper working…")
    elif event["type"] == "usage":
        session["cost"] += event["usage"].get("cost", 0)


def show_context(session):
    """A bar of the desk: each color is one kind of thing, the dots are free space."""
    parts = desk_breakdown(session["messages"], tool_schemas(session_tools(session)))
    guess = sum(parts.values())
    if session["tokens"] and guess:  # the API's count is real: scale our rough split to match it
        parts = {name: round(tokens * session["tokens"] / guess) for name, tokens in parts.items()}
    limit, width = session["desk_limit"], 50
    colors = ["cyan", "blue", "magenta", "yellow", "green", "white"]
    cells = [max(1, round(tokens / limit * width)) if tokens else 0 for tokens in parts.values()]
    bar = "".join(f"[{color}]{'■' * n}[/]" for color, n in zip(colors, cells))
    bar += f"[dim]{'·' * max(0, width - sum(cells))}[/]"
    used = session["tokens"] or sum(parts.values())
    about = "" if session["tokens"] else "≈"
    console.print(f"  {bar}\n  [bold]{about}{used:,}[/] of {limit:,} tokens ({used / limit:.0%})")
    for (name, tokens), color in zip(parts.items(), colors):
        console.print(f"  [{color}]■[/] {name:24} ≈{tokens:,}")
    if not session["tokens"]:
        console.print("  [dim]An estimate. The next request brings the real count.[/]")


def answer(session, task):
    """Send one message and show everything that happens until Cato is done."""
    messages = session["messages"]
    messages.append({"role": "user", "content": with_reminders(task, first=len(messages) == 1)})
    screen = Screen()
    screen.spin()
    ask = lambda name, arguments, why: ask_permission(session, screen, name, arguments, why)
    report = lambda event: show_helper_event(session, screen, event)
    try:
        for event in run_agent(messages, session["model"], tools=session_tools(session, ask, report),
                               ask=ask, settings=session["settings"], desk_limit=session["desk_limit"],
                               max_turns=session["max_turns"], max_cost=session["max_cost"]):
            if event["type"] == "text":
                screen.add_words(event["text"])
            elif event["type"] == "tool_start":
                screen.stop()
                show_tool_start(event)
                screen.spin("Running…")
            elif event["type"] == "tool_end":
                screen.stop()
                show_tool_end(event)
                screen.spin()
            elif event["type"] == "usage":
                usage = event["usage"]
                session["cost"] += usage.get("cost", 0)
                session["tokens"] = usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)
                cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
                session["cache"] = cached / usage["prompt_tokens"] if usage.get("prompt_tokens") else 0
            elif event["type"] == "compact":
                screen.stop()
                session["cost"] += event["cost"]
                session["tokens"] = 0            # unknown until the next request
                console.print(f"[magenta]  ✻ Cleared the desk: {event['how']} "
                              f"({event['before']:,} → ≈{event['after']:,} tokens).[/]")
                screen.spin()
            elif event["type"] == "done":
                screen.stop()
                if event["reason"] != "end":
                    console.print(f"[yellow]  Stopped: {event['reason']}.[/]")
    except KeyboardInterrupt:
        screen.stop()
        repair(messages)
        console.print("[red]  Interrupted.[/] [dim]Tell Cato what to do instead.[/]")
    except (ModelError, httpx.HTTPError) as error:
        screen.stop()
        repair(messages)
        console.print(f"[red]  Error: {escape(str(error))}[/]")
    finally:
        screen.stop()
    console.print(f"[dim]  {status_line(session)}[/]")


# ---------------------------------------------------------------- slash commands

def run_command(session, line):
    name, _, rest = line.partition(" ")
    rest = rest.strip()
    if name in ("/exit", "/quit"):
        return "exit"
    if name == "/help":
        console.print(HELP)
    elif name == "/model":
        if rest:
            session["model"] = rest
        console.print(f"  model: [cyan]{escape(session['model'])}[/]  "
                      f"[dim](choices: {', '.join(MODELS)}, or any OpenRouter id)[/]")
    elif name == "/cost":
        console.print(f"  {session['tokens']:,} tokens on the desk · ${session['cost']:.4f} so far")
    elif name == "/mode":
        if rest in MODES:
            session["settings"]["mode"] = rest
        elif rest:
            console.print(f"  [red]No mode called {escape(rest)}.[/]")
        console.print(f"  mode: [yellow]{session['settings']['mode']}[/]  [dim](choices: {', '.join(MODES)})[/]")
    elif name == "/permissions":
        for kind, color in (("allow", "green"), ("ask", "yellow"), ("deny", "red")):
            rules = ", ".join(session["settings"][kind]) or "(none)"
            console.print(f"  [{color}]{kind:5}[/] {escape(rules)}")
    elif name == "/context":
        show_context(session)
    elif name == "/compact":
        if len(session["messages"]) < 3:
            console.print("  [dim]Nothing to summarize yet.[/]")
            return
        with console.status("[magenta]Summarizing…[/]"):
            usage = summarize(session["messages"], session["model"], tool_schemas(session_tools(session)))
        session["cost"] += usage.get("cost", 0)
        session["tokens"] = 0                    # unknown until the next request
        console.print("  [magenta]✻ The chat is now one summary note.[/] Try /context.")
    elif name == "/memory":
        files = memory_files()
        for path in files:
            console.print(f"  {escape(str(path))}")
        if not files:
            console.print("  [dim]No CATO.md files yet. Start a line with # to add a note.[/]")
    elif name == "/clear":
        session["messages"][1:] = []
        session["tokens"] = 0
        console.print("  [dim]Fresh chat. The cost so far is kept.[/]")
    elif name == "/agents":
        for helper, card in all_helpers().items():
            console.print(f"  [green]{escape(helper)}[/]  [dim]{escape(card['description'])}[/]")
    elif name == "/skills":
        skills = find_cards("skills")
        for skill, card in skills.items():
            console.print(f"  [green]{escape(skill)}[/]  [dim]{escape(card['description'])}[/]")
        if not skills:
            console.print("  [dim]No skills yet. Add one as .cato/skills/<name>/SKILL.md.[/]")
    elif name == "/mcp":
        for server in session["mcp_servers"]:
            names = [t.name for t in session["mcp_tools"] if t.name.startswith(f"mcp__{server['name']}__")]
            console.print(f"  [green]{escape(server['name'])}[/]  {escape(', '.join(names))}")
        for problem in session["mcp_problems"]:
            console.print(f"  [red]{escape(problem)}[/]")
        if not session["mcp_servers"] and not session["mcp_problems"]:
            console.print("  [dim]No servers. List them in .mcp.json.[/]")
    elif name[1:] in find_cards("commands"):        # your own command: a prompt written once
        return ("prompt", fill(find_cards("commands")[name[1:]]["body"], rest))
    elif name[1:] in find_cards("skills"):          # a skill, run by hand
        return ("prompt", fill(find_cards("skills")[name[1:]]["body"], rest))
    else:
        console.print(f"  [red]Unknown command {escape(name)}.[/] Try /help.")


# ---------------------------------------------------------------- the main loop

def banner(session):
    console.print(Panel(
        f"[cyan]φ[/] [bold]Cato Code[/] v{__version__}\n"
        f"[dim]{escape(os.getcwd())}\nmodel: {escape(session['model'])} · /help for commands[/]",
        border_style="cyan", expand=False, padding=(0, 2)))


def repl(args):
    session = {
        "model": args.model,
        "messages": [{"role": "system", "content": system_prompt()}],
        "cost": 0.0, "tokens": 0,
        "max_turns": args.max_turns, "max_cost": args.max_cost,
        "settings": load_settings(args.mode),
        "desk_limit": args.desk_limit or DESK_LIMIT, "cache": 0.0,
        "inputs": Path(args.inputs).read_text().splitlines() if args.inputs else None,
    }
    if session["inputs"] is None:  # a real keyboard: an input box with history
        history = Path.home() / ".cato" / "history"
        history.parent.mkdir(exist_ok=True)
        keys = KeyBindings()

        @keys.add("s-tab")  # Shift+Tab: the next mode, like Claude Code
        def next_mode(event):
            modes = session["settings"]
            modes["mode"] = MODES[(MODES.index(modes["mode"]) + 1) % len(MODES)]

        keyboard = PromptSession(history=FileHistory(str(history)), key_bindings=keys)
    banner(session)
    servers = load_servers(lambda name, config: approve_server(session, name, config))
    session["mcp_servers"], session["mcp_tools"], session["mcp_problems"] = servers
    if session["mcp_servers"] or session["mcp_problems"]:
        run_command(session, "/mcp")
    while True:
        console.print()
        try:
            if session["inputs"] is None:
                line = keyboard.prompt("> ", bottom_toolbar=lambda: status_line(session))
            else:
                line = read_line(session, "[yellow]>[/] ")
        except KeyboardInterrupt:
            continue
        except EOFError:
            break
        line = line.strip()
        if not line:
            continue
        if line.startswith("/"):
            result = run_command(session, line)
            if result == "exit":
                break
            if isinstance(result, tuple):   # a command that turns into a message for Cato
                answer(session, result[1])
            continue
        answer(session, line)
    stop_servers(session["mcp_servers"])
    if args.svg:
        console.save_svg(args.svg, title="cato", theme=PHILO_THEME)
