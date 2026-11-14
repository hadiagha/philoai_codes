"""The agent loop: ask, act, look, repeat. It hands out events; a screen shows them."""
import json
import os

from .model import stream_model
from .tools import TOOLS, find_tool, run_tool, tool_schemas

MAX_TURNS = 30


def system_prompt():
    return (
        "You are Cato, a coding assistant working in a terminal.\n"
        f"The current folder is {os.getcwd()}.\n"
        "Use Glob and Grep to find code, Read to look at it, and Edit to change it. "
        "Read a file before you edit it. Use Bash to run tests and commands. "
        "Make the smallest change that solves the task. "
        "When the task is done, reply with a short summary."
    )


def describe(name, arguments):
    """A one-line view of a tool call, like Read(shop.py)."""
    try:
        args = json.loads(arguments or "{}")
    except json.JSONDecodeError:
        return f"{name}(?)"
    if not isinstance(args, dict) or not args:
        return f"{name}()"
    keys = [k for k in ("file_path", "command", "pattern", "description") if k in args]
    first = str(args[keys[0]] if keys else next(iter(args.values())))
    return f"{name}({first.splitlines()[0][:60] if first.strip() else ''})"


def run_agent(messages, model, tools=TOOLS, ask=None, max_turns=MAX_TURNS, max_cost=None):
    """Run until the model stops asking for tools, handing out an event for each step.

    ask(name, arguments) is called before any tool that changes things; it returns True or False.
    Events are small dicts: text, tool_start, tool_end, usage, and done.
    """
    schemas = tool_schemas(tools)
    cost = 0.0
    for turn in range(1, max_turns + 1):
        if max_cost is not None and cost >= max_cost:
            yield {"type": "done", "text": "", "reason": f"cost limit ${max_cost}", "turns": turn - 1}
            return
        for piece in stream_model(messages, schemas, model):
            if piece[0] == "text":
                yield {"type": "text", "text": piece[1]}
            else:
                reply, usage = piece[1], piece[2]
        messages.append(reply)
        cost += usage.get("cost", 0)
        yield {"type": "usage", "usage": usage}

        if not reply.get("tool_calls"):
            yield {"type": "done", "text": reply.get("content") or "", "reason": "end", "turns": turn}
            return

        for call in reply["tool_calls"]:
            name, arguments = call["function"]["name"], call["function"]["arguments"]
            yield {"type": "tool_start", "id": call["id"], "name": name, "arguments": arguments}
            tool = find_tool(name, tools)
            if tool and not tool.read_only and not (ask and ask(name, arguments)):
                output, ok = "The user said no. Ask them what to do instead.", False
            else:
                output, ok = run_tool(name, arguments, tools)
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": output})
            yield {"type": "tool_end", "id": call["id"], "name": name, "output": output, "ok": ok}

    yield {"type": "done", "text": "", "reason": f"turn limit ({max_turns})", "turns": max_turns}


def repair(messages):
    """After a stop, every tool request still needs an answer, or the next call fails."""
    for message in reversed(messages):
        if message["role"] == "assistant":
            answered = {m.get("tool_call_id") for m in messages if m["role"] == "tool"}
            for call in message.get("tool_calls") or []:
                if call["id"] not in answered:
                    messages.append({"role": "tool", "tool_call_id": call["id"],
                                     "content": "Stopped by the user before this finished."})
            return
