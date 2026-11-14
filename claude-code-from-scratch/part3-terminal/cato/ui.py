"""The screen: an input box, streamed answers, tool lines, diffs and a status line.

The loop never prints. It hands out events, and this file decides how each one looks.
"""
import json
import os
from pathlib import Path

import httpx
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel
from rich.terminal_theme import TerminalTheme

from . import __version__
from .agent import describe, repair, run_agent, system_prompt
from .model import MODELS, ModelError

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
  /clear          start a fresh chat
  /exit           quit (or Ctrl+D)
[dim]Ctrl+C stops Cato in the middle of an answer.[/]"""


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


def ask_permission(session, screen, name, arguments):
    """Called by the loop before a tool that changes things. True means go ahead."""
    screen.stop()
    try:
        command = json.loads(arguments).get("command")
    except (json.JSONDecodeError, AttributeError):
        command = None
    what = f"run [bold]{escape(command)}[/]" if command else f"use {escape(describe(name, arguments))}"
    console.print(f"  [yellow]Cato wants to {what}[/]")
    answer = read_line(session, "  Allow? [bold](y/n)[/] ").strip().lower()
    screen.spin("Running…")
    return answer in ("y", "yes")


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
    return (f"{session['model']} · {session['tokens']:,} tokens on the desk · "
            f"${session['cost']:.4f} · /help")


def answer(session, task):
    """Send one message and show everything that happens until Cato is done."""
    messages = session["messages"]
    messages.append({"role": "user", "content": task})
    screen = Screen()
    screen.spin()
    try:
        for event in run_agent(messages, session["model"],
                               ask=lambda name, arguments: ask_permission(session, screen, name, arguments),
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
    elif name == "/clear":
        session["messages"][1:] = []
        session["tokens"] = 0
        console.print("  [dim]Fresh chat. The cost so far is kept.[/]")
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
        "inputs": Path(args.inputs).read_text().splitlines() if args.inputs else None,
    }
    if session["inputs"] is None:  # a real keyboard: an input box with history
        history = Path.home() / ".cato" / "history"
        history.parent.mkdir(exist_ok=True)
        keyboard = PromptSession(history=FileHistory(str(history)))
    banner(session)
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
            if run_command(session, line) == "exit":
                break
            continue
        answer(session, line)
    if args.svg:
        console.save_svg(args.svg, title="cato", theme=PHILO_THEME)
