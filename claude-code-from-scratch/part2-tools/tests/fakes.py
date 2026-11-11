"""A fake model for tests: scripted answers, sent as streamed pieces like OpenRouter's."""
import json

from cato import model


def pieces(text=None, calls=(), usage=None, reasoning=None):
    """One scripted answer as a list of stream pieces (text in 5-character bits)."""
    out = []
    if reasoning:
        for i in range(0, len(reasoning), 6):
            out.append({"choices": [{"delta": {"reasoning_details": [
                {"type": "reasoning.text", "index": 0, "text": reasoning[i:i + 6]}]}}]})
    for i in range(0, len(text or ""), 5):
        out.append({"choices": [{"delta": {"content": text[i:i + 5]}}]})
    for index, (name, args) in enumerate(calls):
        arguments = json.dumps(args)
        out.append({"choices": [{"delta": {"tool_calls": [{"index": index, "id": f"call_{index}",
                    "type": "function", "function": {"name": name, "arguments": ""}}]}}]})
        for i in range(0, len(arguments), 7):
            out.append({"choices": [{"delta": {"tool_calls": [
                {"index": index, "function": {"arguments": arguments[i:i + 7]}}]}}]})
    out.append({"choices": [{"delta": {}, "finish_reason": "tool_calls" if calls else "stop"}],
                "usage": usage or {"prompt_tokens": 100, "completion_tokens": 10, "cost": 0.001}})
    return out


def use_script(tmp_path, *answers):
    """Make the model replay these answers, in order, with no delay."""
    cassette = tmp_path / "script.jsonl"
    cassette.write_text("".join(json.dumps(a) + "\n" for a in answers))
    model.replay_file, model._recorded, model.replay_delay = str(cassette), None, 0
    return cassette
