"""Talking to the AI, through OpenRouter, with the answer streamed piece by piece."""
import json
import os
import time

import httpx

API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Short names for the five models in this series, and their OpenRouter ids.
MODELS = {
    "sonnet": "anthropic/claude-sonnet-5.5",
    "opus": "anthropic/claude-opus-5.5",
    "sol": "openai/gpt-6.1-sol",
    "terra": "openai/gpt-6.1-terra",
    "gemini": "google/gemini-4-argon",
}
DEFAULT_MODEL = os.environ.get("CATO_MODEL", "terra")

# Record and replay: save real answers once, then play them back for free.
record_file = None    # set by --record
replay_file = None    # set by --replay
replay_delay = 0.02   # seconds between pieces when replaying, so it still looks live
_recorded = None      # the answers waiting to be replayed


class ModelError(Exception):
    """The API said no: a bad key, no credit, or a model that's down."""


def model_id(name):
    return MODELS.get(name, name)  # a short name, or any full OpenRouter id


def live_pieces(body):
    """Send the request and hand out each piece of the answer as it arrives."""
    headers = {"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"}
    with httpx.stream("POST", API_URL, headers=headers, json=body, timeout=300) as response:
        if response.status_code != 200:
            response.read()
            raise ModelError(f"{response.status_code}: {response.text[:300]}")
        for line in response.iter_lines():
            if not line.startswith("data:"):
                continue                       # blank lines and ": OPENROUTER PROCESSING"
            data = line[5:].strip()
            if data == "[DONE]":
                return
            yield json.loads(data)


def replayed_pieces():
    """Hand out the next recorded answer, piece by piece, like the real thing."""
    global _recorded
    if _recorded is None:
        with open(replay_file) as f:
            _recorded = [json.loads(line) for line in f if line.strip()]
    if not _recorded:
        raise ModelError(f"The recording {replay_file} has no more answers.")
    for piece in _recorded.pop(0):
        time.sleep(replay_delay)
        yield piece


def glue_tool_call(calls, piece):
    """Tool calls arrive in fragments. Join them by their index."""
    call = calls.setdefault(piece.get("index", 0), {"id": "", "name": "", "arguments": ""})
    call["id"] = piece.get("id") or call["id"]
    function = piece.get("function") or {}
    call["name"] = call["name"] or function.get("name") or ""
    call["arguments"] += function.get("arguments") or ""


def glue_reasoning(details, piece):
    """Some models send hidden reasoning that must be sent back unchanged next turn."""
    for old in details:
        if old.get("index") == piece.get("index") and old.get("type") == piece.get("type"):
            for key, value in piece.items():
                if key in ("text", "summary", "data") and isinstance(value, str):
                    old[key] = old.get(key, "") + value
                elif value is not None:
                    old[key] = value
            return
    details.append(dict(piece))


def stream_model(messages, tools, model):
    """Hand out ("text", words) as they arrive, then ("reply", message, usage) at the end."""
    body = {"model": model_id(model), "messages": messages, "tools": tools, "stream": True}
    pieces = replayed_pieces() if replay_file else live_pieces(body)
    text, calls, reasoning, usage, seen = [], {}, [], {}, []
    for piece in pieces:
        seen.append(piece)
        if "error" in piece:
            raise ModelError(piece["error"].get("message", "the stream failed"))
        usage = piece.get("usage") or usage
        for choice in piece.get("choices", []):
            delta = choice.get("delta") or {}
            if delta.get("content"):
                text.append(delta["content"])
                yield ("text", delta["content"])
            for call_piece in delta.get("tool_calls") or []:
                glue_tool_call(calls, call_piece)
            for detail in delta.get("reasoning_details") or []:
                glue_reasoning(reasoning, detail)
    if record_file:
        with open(record_file, "a") as f:
            f.write(json.dumps(seen) + "\n")

    reply = {"role": "assistant", "content": "".join(text) or None}
    if calls:
        reply["tool_calls"] = [
            {"id": call["id"] or f"call_{index}", "type": "function",
             "function": {"name": call["name"], "arguments": call["arguments"] or "{}"}}
            for index, call in sorted(calls.items())]
    if reasoning:
        reply["reasoning_details"] = reasoning
    yield ("reply", reply, usage)
