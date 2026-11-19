"""A PostToolUse hook: after every edit to a .py file, check that it still compiles.

If it doesn't, exit code 2 sends the error back to the model, so it can fix it.
"""
import json
import py_compile
import sys

call = json.load(sys.stdin)
path = call["tool_input"].get("file_path", "")
if path.endswith(".py"):
    try:
        py_compile.compile(path, doraise=True)
    except py_compile.PyCompileError as error:
        print(f"{path} no longer compiles:\n{error.msg}", file=sys.stderr)
        sys.exit(2)
