"""A PreToolUse hook: Cato may not change the tests or the secrets file.

Cato sends the tool call as JSON on stdin. Exit code 2 stops it, and stderr tells the model why.
"""
import json
import sys
from pathlib import Path

call = json.load(sys.stdin)
name = Path(call["tool_input"].get("file_path", "")).name
if name == ".env" or name.startswith("test_"):
    print(f"{name} is protected: fix the code, not the tests or the secrets.", file=sys.stderr)
    sys.exit(2)
