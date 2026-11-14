"""Start Cato.

    cato                       the full screen, like Claude Code
    cato -p "fix the test"     no screen: run one task and print the answer
"""
import argparse
import json
import sys
import time

from . import model
from .agent import MAX_TURNS, describe, run_agent, system_prompt
from .model import DEFAULT_MODEL, MODELS, ModelError


def headless(args):
    """The same loop with a different listener: no screen, just the final answer."""
    messages = [{"role": "system", "content": system_prompt()},
                {"role": "user", "content": args.print}]
    stats = {"turns": 0, "cost": 0.0, "tokens": 0, "reason": "", "seconds": 0.0}
    result, start = "", time.time()
    try:
        for event in run_agent(messages, args.model, ask=lambda name, arguments: args.yes,
                               max_turns=args.max_turns, max_cost=args.max_cost):
            if event["type"] == "tool_start" and args.verbose:
                print("●", describe(event["name"], event["arguments"]), file=sys.stderr)
            elif event["type"] == "usage":
                stats["cost"] += event["usage"].get("cost", 0)
                stats["tokens"] += (event["usage"].get("prompt_tokens", 0)
                                    + event["usage"].get("completion_tokens", 0))
            elif event["type"] == "done":
                result, stats["turns"], stats["reason"] = event["text"], event["turns"], event["reason"]
    except ModelError as error:
        stats["reason"] = f"error: {error}"
    stats["seconds"] = round(time.time() - start, 1)
    print(json.dumps({"result": result, **stats}) if args.json else result)


def main():
    parser = argparse.ArgumentParser(prog="cato", description="Cato Code: a Claude Code clone.")
    parser.add_argument("-p", "--print", metavar="TASK", help="run one task without the screen")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"{', '.join(MODELS)}, or any OpenRouter id (default {DEFAULT_MODEL})")
    parser.add_argument("--yes", action="store_true", help="with -p: allow every tool")
    parser.add_argument("--json", action="store_true", help="with -p: print the answer and stats as JSON")
    parser.add_argument("--verbose", action="store_true", help="with -p: list tool calls on stderr")
    parser.add_argument("--max-turns", type=int, default=MAX_TURNS, help="stop a task after this many turns")
    parser.add_argument("--max-cost", type=float, help="stop a task after this many dollars")
    parser.add_argument("--record", metavar="FILE", help="save every model answer to FILE")
    parser.add_argument("--replay", metavar="FILE", help="answer from a recording, not the API")
    parser.add_argument("--inputs", metavar="FILE", help="read your messages from FILE (for demos)")
    parser.add_argument("--svg", metavar="FILE", help="save the screen as an SVG when Cato exits")
    args = parser.parse_args()

    model.record_file, model.replay_file = args.record, args.replay
    if args.print is not None:
        headless(args)
    else:
        from .ui import repl  # the screen libraries load only when there is a screen
        repl(args)


if __name__ == "__main__":
    main()
