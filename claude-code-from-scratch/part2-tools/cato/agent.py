"""The agent loop: ask, act, look, repeat."""
import json
import os

from .model import ask_model
from .tools import TOOLS, run_tool, tool_schemas

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


def confirm(tool, arguments):
    """Tools that only read run straight away. Anything else asks first."""
    if tool is None or tool.read_only:
        return True
    return input("  Allow? [y/n] ").strip().lower() == "y"


def agent_loop(messages, model, tools=TOOLS, max_turns=MAX_TURNS):
    """Run until the model stops asking for tools. Returns its final answer."""
    schemas = tool_schemas(tools)
    for turn in range(max_turns):
        reply, usage = ask_model(messages, schemas, model)
        messages.append(reply)
        print(f"  [{usage.get('prompt_tokens', 0)} tokens in, "
              f"{usage.get('completion_tokens', 0)} out, ${usage.get('cost', 0):.4f}]")
        if not reply.get("tool_calls"):
            return reply.get("content") or ""
        for call in reply["tool_calls"]:
            name, arguments = call["function"]["name"], call["function"]["arguments"]
            print(f"● {describe(name, arguments)}")
            tool = next((t for t in tools if t.name == name), None)
            if confirm(tool, arguments):
                output, ok = run_tool(name, arguments, tools)
            else:
                output, ok = "The user said no. Ask them what to do instead.", False
            preview = output.splitlines()[:4]
            print("  └ " + "\n    ".join(preview))
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": output})
    return f"Stopped after {max_turns} turns."
