"""Cato Code, Part 1: the agent loop.

One model, one tool (bash), and a loop. Run it inside the folder you want it to work on:

    export OPENROUTER_API_KEY=...
    python cato.py
"""
import json
import os
import subprocess

import httpx

API_URL = "https://openrouter.ai/api/v1/chat/completions"
API_KEY = os.environ["OPENROUTER_API_KEY"]
MODEL = os.environ.get("CATO_MODEL", "openai/gpt-6.1-terra")
MAX_TURNS = 20

SYSTEM_PROMPT = (
    "You are Cato, a coding assistant working in a terminal. "
    f"The current folder is {os.getcwd()}. "
    "Use the bash tool to look around, run code and change files. "
    "When the task is done, reply with a short summary."
)

# The form the model fills in when it wants to run a command.
BASH_TOOL = {
    "type": "function",
    "function": {
        "name": "bash",
        "description": "Run a shell command in the current folder and return what it prints.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The command to run."},
            },
            "required": ["command"],
        },
    },
}


def ask_model(messages):
    """Send the whole chat to the model and return its reply."""
    response = httpx.post(
        API_URL,
        headers={"Authorization": f"Bearer {API_KEY}"},
        json={"model": MODEL, "messages": messages, "tools": [BASH_TOOL]},
        timeout=300,
    )
    response.raise_for_status()
    data = response.json()
    usage = data["usage"]
    print(f"  [{usage['prompt_tokens']} tokens in, "
          f"{usage['completion_tokens']} out, ${usage.get('cost', 0):.4f}]")
    return data["choices"][0]["message"]


def run_bash(command):
    """Ask the user first, then run the command and return its output as text."""
    if input("  Run it? [y/n] ").strip().lower() != "y":
        return "The user said no. Ask them what to do instead."
    try:
        result = subprocess.run(command, shell=True, capture_output=True,
                                text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return "Error: the command took longer than 60 seconds."
    output = (result.stdout + result.stderr)[-10_000:]  # errors are at the end
    return output or "(no output)"


def agent_loop(messages):
    """Ask, act, look, repeat, until the model stops asking for tools."""
    for turn in range(MAX_TURNS):
        reply = ask_model(messages)
        messages.append(reply)
        if not reply.get("tool_calls"):          # no request: the model is done
            return reply.get("content") or ""
        for call in reply["tool_calls"]:         # it can ask for several at once
            command = json.loads(call["function"]["arguments"])["command"]
            print(f"  $ {command}")
            output = run_bash(command)
            print("  " + "\n  ".join(output.splitlines()[:5]))
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": output})
    return f"Stopped after {MAX_TURNS} turns."


def main():
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    print(f"Cato v0.1 · {MODEL} · type a task, or 'exit'")
    while True:
        task = input("\n> ")
        if task.strip() in ("exit", "quit"):
            break
        messages.append({"role": "user", "content": task})
        print(agent_loop(messages))


if __name__ == "__main__":
    main()
