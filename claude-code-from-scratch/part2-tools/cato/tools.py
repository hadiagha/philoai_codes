"""The six tools Cato can use, and the one path every tool call goes through."""
import difflib
import fnmatch
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

MAX_OUTPUT = 20_000      # characters handed back to the model, at most
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".cato"}


@dataclass
class Tool:
    name: str             # what the model calls it
    description: str      # when and how to use it, written for the model
    parameters: dict      # the form the model fills in (JSON Schema)
    function: Callable    # the Python function that does the work
    read_only: bool = False  # True if it never changes anything


# ---------------------------------------------------------------- helpers

# Files the model has read, and when they were last changed (their "mtime").
# Edit and Write use this to make sure the model has seen the current version.
files_read = {}


def full_path(file_path):
    """Turn a path from the model into an absolute path inside the current folder."""
    path = Path(file_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def remember_read(path):
    files_read[str(path)] = path.stat().st_mtime


def check_read_first(path):
    """Edits are only safe on a file the model has read, and nobody changed since."""
    if str(path) not in files_read:
        raise ValueError(f"Read {path} before changing it.")
    if path.stat().st_mtime != files_read[str(path)]:
        raise ValueError(f"{path} changed since you read it. Read it again first.")


def make_diff(path, old_text, new_text):
    """A short unified diff, so the model and the user can see what changed."""
    lines = difflib.unified_diff(old_text.splitlines(), new_text.splitlines(),
                                 f"a/{path.name}", f"b/{path.name}", n=2, lineterm="")
    return "\n".join(lines)


def short(path):
    """Show paths inside the current folder without the long prefix."""
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def walk_files(root):
    """Every file under root, skipping folders like .git and node_modules."""
    for folder, subfolders, files in os.walk(root):
        subfolders[:] = sorted(d for d in subfolders if d not in SKIP_DIRS)
        for name in sorted(files):
            yield Path(folder) / name


# ---------------------------------------------------------------- the tools

def read_file(file_path, offset=1, limit=2000):
    path = full_path(file_path)
    if path.is_dir():
        raise ValueError(f"{path} is a folder. Use Glob or Bash ls to list it.")
    lines = path.read_text(errors="replace").splitlines()
    remember_read(path)
    if not lines:
        return "(the file is empty)"
    start = max(offset, 1) - 1
    chunk = lines[start:start + limit]
    numbered = [f"{start + i + 1:6}\t{line[:2000]}" for i, line in enumerate(chunk)]
    if start + limit < len(lines):
        numbered.append(f"... {len(lines) - start - limit} more lines. "
                        f"Use offset={start + limit + 1} to read on.")
    return "\n".join(numbered)


def write_file(file_path, content):
    path = full_path(file_path)
    old_text = ""
    if path.exists():
        check_read_first(path)
        old_text = path.read_text(errors="replace")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    remember_read(path)
    if not old_text:
        return f"Created {short(path)} ({len(content.splitlines())} lines)."
    return f"Wrote {short(path)}.\n{make_diff(path, old_text, content)}"


def edit_file(file_path, old_string, new_string, replace_all=False):
    path = full_path(file_path)
    check_read_first(path)
    text = path.read_text()
    count = text.count(old_string)
    if old_string == "" or count == 0:
        raise ValueError("old_string was not found. Copy the text exactly as Read shows it, "
                         "without the line numbers.")
    if count > 1 and not replace_all:
        raise ValueError(f"old_string appears {count} times. Add nearby lines to make it "
                         "unique, or set replace_all to true.")
    new_text = text.replace(old_string, new_string)
    path.write_text(new_text)
    remember_read(path)
    return f"Edited {short(path)}.\n{make_diff(path, text, new_text)}"


def run_bash(command, timeout=120):
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True,
                                timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ValueError(f"The command took longer than {timeout} seconds and was stopped.")
    output = result.stdout + result.stderr
    if result.returncode != 0:
        output += f"\n(exit code {result.returncode})"
    return output.strip() or "(no output)"


def glob_files(pattern, path="."):
    root = full_path(path)
    matches = [p for p in root.glob(pattern)
               if p.is_file() and not SKIP_DIRS & set(p.relative_to(root).parts)]
    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)  # newest first
    if not matches:
        return "No files found."
    shown = [str(p.relative_to(root)) for p in matches[:100]]
    if len(matches) > 100:
        shown.append(f"... and {len(matches) - 100} more. Use a narrower pattern.")
    return "\n".join(shown)


def grep_files(pattern, path=".", glob="*", ignore_case=False):
    regex = re.compile(pattern, re.IGNORECASE if ignore_case else 0)
    root = full_path(path)
    files = [root] if root.is_file() else walk_files(root)
    hits = []
    for file in files:
        if not fnmatch.fnmatch(file.name, glob):
            continue
        try:
            text = file.read_text()
        except (UnicodeDecodeError, OSError):
            continue  # skip pictures, binaries and unreadable files
        for number, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                hits.append(f"{short(file)}:{number}: {line.strip()[:200]}")
                if len(hits) == 100:
                    return "\n".join(hits) + "\n... stopped at 100 matches. Narrow the search."
    return "\n".join(hits) or "No matches."


TOOLS = [
    Tool(
        name="Read",
        description="Read a text file. Lines come back numbered like '     7\\tcode'. "
                    "The numbers are not part of the file. Read a file before you edit it. "
                    "For big files, use offset and limit to read part of it.",
        parameters={"type": "object", "properties": {
            "file_path": {"type": "string", "description": "Path to the file."},
            "offset": {"type": "integer", "description": "First line to read (1 = top)."},
            "limit": {"type": "integer", "description": "How many lines to read."},
        }, "required": ["file_path"]},
        function=read_file, read_only=True),
    Tool(
        name="Write",
        description="Create a new file, or replace a whole file. To change part of an "
                    "existing file, use Edit instead.",
        parameters={"type": "object", "properties": {
            "file_path": {"type": "string", "description": "Path to the file."},
            "content": {"type": "string", "description": "The full new content."},
        }, "required": ["file_path", "content"]},
        function=write_file),
    Tool(
        name="Edit",
        description="Change part of a file by exact find-and-replace. old_string must "
                    "match the file exactly (spaces too) and appear only once, unless "
                    "replace_all is true. Read the file first.",
        parameters={"type": "object", "properties": {
            "file_path": {"type": "string", "description": "Path to the file."},
            "old_string": {"type": "string", "description": "The exact text to replace."},
            "new_string": {"type": "string", "description": "The text to put there."},
            "replace_all": {"type": "boolean", "description": "Replace every match."},
        }, "required": ["file_path", "old_string", "new_string"]},
        function=edit_file),
    Tool(
        name="Bash",
        description="Run a shell command in the current folder, for things like running "
                    "tests, git and installing packages. Don't use it to read or edit "
                    "files; use Read and Edit.",
        parameters={"type": "object", "properties": {
            "command": {"type": "string", "description": "The command to run."},
            "timeout": {"type": "integer", "description": "Seconds before it is stopped (default 120)."},
        }, "required": ["command"]},
        function=run_bash),
    Tool(
        name="Glob",
        description="Find files by name pattern, like '**/*.py' or 'src/*.js'. "
                    "Newest files come first.",
        parameters={"type": "object", "properties": {
            "pattern": {"type": "string", "description": "The name pattern."},
            "path": {"type": "string", "description": "Folder to search (default: here)."},
        }, "required": ["pattern"]},
        function=glob_files, read_only=True),
    Tool(
        name="Grep",
        description="Search inside files with a regular expression. Returns "
                    "file:line: text for each match.",
        parameters={"type": "object", "properties": {
            "pattern": {"type": "string", "description": "Regular expression to find."},
            "path": {"type": "string", "description": "File or folder (default: here)."},
            "glob": {"type": "string", "description": "Only files whose name matches, like '*.py'."},
            "ignore_case": {"type": "boolean", "description": "Ignore upper/lower case."},
        }, "required": ["pattern"]},
        function=grep_files, read_only=True),
]


# ---------------------------------------------------------------- one path for every call

def find_tool(name, tools=TOOLS):
    for tool in tools:
        if tool.name == name:
            return tool
    return None


def tool_schemas(tools=TOOLS):
    """The tool list in the format the API expects."""
    return [{"type": "function", "function": {"name": t.name, "description": t.description,
                                              "parameters": t.parameters}}
            for t in tools]


JSON_TYPES = {"string": str, "integer": int, "number": (int, float),
              "boolean": bool, "object": dict, "array": list}


def check_form(tool, args):
    """Is every required box filled in, with the right kind of value?"""
    for name in tool.parameters.get("required", []):
        if name not in args:
            raise ValueError(f"Missing required field '{name}'.")
    for name, value in args.items():
        spec = tool.parameters["properties"].get(name)
        if spec is None:
            raise ValueError(f"Unknown field '{name}'.")
        expected = JSON_TYPES[spec["type"]]
        if not isinstance(value, expected) or (spec["type"] == "integer" and isinstance(value, bool)):
            raise ValueError(f"Field '{name}' should be of type {spec['type']}.")


def trim(text, limit=MAX_OUTPUT):
    """Keep the start and the end of long output; the middle is usually the least useful."""
    if len(text) <= limit:
        return text
    half = limit // 2
    return f"{text[:half]}\n\n... [{len(text) - limit} characters cut] ...\n\n{text[-half:]}"


def run_tool(name, arguments, tools=TOOLS):
    """Look it up → check the form → run → trim. Errors become results the model can read.

    Returns (text for the model, True if it worked).
    """
    tool = find_tool(name, tools)
    if tool is None:
        return f"Error: there is no tool called {name}.", False
    try:
        args = json.loads(arguments or "{}")
    except json.JSONDecodeError as error:
        return f"Error: the arguments were not valid JSON ({error}).", False
    try:
        check_form(tool, args)
        output = tool.function(**args)
    except Exception as error:  # any failure goes back to the model as text
        return f"Error: {error}", False
    return trim(str(output)), True
