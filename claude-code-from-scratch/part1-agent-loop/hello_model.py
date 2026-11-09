import os
import httpx

response = httpx.post(
    "https://openrouter.ai/api/v1/chat/completions",
    headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
    json={
        "model": "anthropic/claude-sonnet-5.5",
        "messages": [
            {"role": "system", "content": "You are a coding assistant."},
            {"role": "user",
             "content": "The tests in test_shop.py fail. Find the bug and fix it."},
        ],
    },
    timeout=120,
)
data = response.json()
print(data["choices"][0]["message"]["content"])
print(data["usage"])
