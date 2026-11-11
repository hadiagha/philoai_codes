"""Talking to the AI, through OpenRouter."""
import os

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
DEFAULT_MODEL = "terra"


class ModelError(Exception):
    """The API said no: a bad key, no credit, or a model that's down."""


def model_id(name):
    return MODELS.get(name, name)  # a short name, or any full OpenRouter id


def ask_model(messages, tools, model):
    """Send the chat and the tool list. Return the reply message and the usage numbers."""
    response = httpx.post(
        API_URL,
        headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
        json={"model": model_id(model), "messages": messages, "tools": tools},
        timeout=300,
    )
    data = response.json()
    if response.status_code != 200 or "error" in data:
        message = data.get("error", {}).get("message", response.text[:300])
        raise ModelError(f"{response.status_code}: {message}")
    return data["choices"][0]["message"], data.get("usage", {})
