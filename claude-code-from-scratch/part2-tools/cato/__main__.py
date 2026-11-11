"""Start Cato: python -m cato [--model terra]"""
import argparse

from . import __version__
from .agent import agent_loop, system_prompt
from .model import DEFAULT_MODEL, MODELS


def main():
    parser = argparse.ArgumentParser(prog="cato", description="A Claude Code clone.")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"one of {', '.join(MODELS)} or any OpenRouter id")
    args = parser.parse_args()

    messages = [{"role": "system", "content": system_prompt()}]
    print(f"Cato v{__version__} · {args.model} · type a task, or 'exit'")
    while True:
        task = input("\n> ")
        if task.strip() in ("exit", "quit"):
            break
        messages.append({"role": "user", "content": task})
        print(agent_loop(messages, args.model))


if __name__ == "__main__":
    main()
