"""Hooks: your own scripts that run at fixed moments around every tool call.

Each hook gets a JSON message on stdin, like
    {"hook_event_name": "PreToolUse", "tool_name": "Edit", "tool_input": {...}, "cwd": "..."}
Exit code 0 means fine. Exit code 2 means stop: what it printed to stderr goes to the model.
"""
import json
import os
import re
import subprocess


def matching_hooks(settings, event, tool_name):
    """The hook commands for this moment whose matcher fits the tool, like "Edit|Write"."""
    for entry in settings["hooks"].get(event, []):
        matcher = entry.get("matcher") or "*"
        if matcher == "*" or re.fullmatch(matcher, tool_name):
            for hook in entry.get("hooks", []):
                yield hook["command"], hook.get("timeout", 60)


def run_hooks(settings, event, tool_name, tool_input, tool_output=None):
    """Run the hooks for one moment. Returns (stopped, message for the model)."""
    message = {"hook_event_name": event, "tool_name": tool_name,
               "tool_input": tool_input, "cwd": os.getcwd()}
    if tool_output is not None:
        message["tool_response"] = tool_output
    for command, timeout in matching_hooks(settings, event, tool_name):
        try:
            result = subprocess.run(command, shell=True, input=json.dumps(message),
                                    capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            continue  # a slow hook never blocks the work
        if result.returncode == 2:
            return True, result.stderr.strip() or f"Stopped by the hook: {command}"
    return False, ""
