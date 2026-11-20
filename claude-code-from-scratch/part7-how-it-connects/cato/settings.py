"""Settings: yours in ~/.cato/settings.json, the project's in .cato/settings.json.

Example:
    {
      "permissions": {
        "defaultMode": "default",
        "allow": ["Bash(git status)", "Bash(pytest *)"],
        "ask":   ["Bash(git push *)"],
        "deny":  ["Bash(rm *)", "Read(.env)"]
      },
      "hooks": {
        "PreToolUse": [{"matcher": "Edit|Write", "hooks": [{"type": "command", "command": "python3 check.py"}]}]
      }
    }
"""
import json
from pathlib import Path


def settings_files():
    return [Path.home() / ".cato" / "settings.json", Path.cwd() / ".cato" / "settings.json"]


def load_settings(mode=None):
    """Read both files and add them together. Lists are joined; the project wins on the mode."""
    settings = {"mode": "default", "allow": [], "ask": [], "deny": [], "hooks": {}}
    for path in settings_files():
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        permissions = data.get("permissions", {})
        for kind in ("allow", "ask", "deny"):
            settings[kind] += permissions.get(kind, [])
        settings["mode"] = permissions.get("defaultMode", settings["mode"])
        for event, entries in data.get("hooks", {}).items():
            settings["hooks"].setdefault(event, []).extend(entries)
    if mode:
        settings["mode"] = mode  # --mode on the command line wins over the files
    return settings
