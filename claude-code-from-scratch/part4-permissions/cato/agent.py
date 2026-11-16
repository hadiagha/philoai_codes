"""The agent loop: ask, act, look, repeat. It hands out events; a screen shows them."""
import json
import os
from concurrent.futures import ThreadPoolExecutor

from .hooks import run_hooks
from .model import stream_model
from .permissions import check_call
from .settings import load_settings
from .tools import TOOLS, find_tool, run_tool, tool_schemas

MAX_TURNS = 30


def system_prompt():
    return (
        "You are Cato, a coding assistant working in a terminal.\n"
        f"The current folder is {os.getcwd()}.\n"
        "Use Glob and Grep to find code, Read to look at it, and Edit to change it. "
        "Read a file before you edit it. Use Bash to run tests and commands. "
        "Make the smallest change that solves the task. "
        "If a tool call is not allowed, don't try to get around it; ask the user. "
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


def group_calls(calls, tools):
    """Calls that only read can run side by side. Anything else runs on its own."""
    groups = []
    for call in calls:
        tool = find_tool(call["function"]["name"], tools)
        reads = bool(tool and tool.read_only)
        if reads and groups and groups[-1]["reads"]:
            groups[-1]["calls"].append(call)
        else:
            groups.append({"reads": reads, "calls": [call]})
    return [group["calls"] for group in groups]


def run_agent(messages, model, tools=TOOLS, ask=None, settings=None,
              max_turns=MAX_TURNS, max_cost=None):
    """Run until the model stops asking for tools, handing out an event for each step.

    ask(name, arguments, why) is called when the rules say "ask"; it returns "yes", "always" or "no".
    Events are small dicts: text, tool_start, tool_end, usage, and done.
    """
    settings = settings or load_settings()
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

        for group in group_calls(reply["tool_calls"], tools):
            # 1. Check each call in order: hooks, rules, and maybe a question for you.
            checked = []
            for call in group:
                name, arguments = call["function"]["name"], call["function"]["arguments"]
                yield {"type": "tool_start", "id": call["id"], "name": name, "arguments": arguments}
                allowed, refusal = check_call(name, arguments, find_tool(name, tools), settings, ask)
                checked.append((call, allowed, refusal))

            # 2. Run the allowed ones. Reads in the same group run side by side.
            def run_one(item):
                call, allowed, refusal = item
                if not allowed:
                    return refusal, False
                return run_tool(call["function"]["name"], call["function"]["arguments"], tools)

            if len(checked) == 1:
                results = [run_one(checked[0])]
            else:
                with ThreadPoolExecutor(max_workers=8) as pool:
                    results = list(pool.map(run_one, checked))

            # 3. Answer every request, in the order the model asked.
            for (call, allowed, _), (output, ok) in zip(checked, results):
                name = call["function"]["name"]
                if allowed and ok:
                    stopped, note = run_hooks(settings, "PostToolUse", name,
                                              json.loads(call["function"]["arguments"] or "{}"), output)
                    if stopped:
                        output += f"\n\nA hook found a problem: {note}"
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
