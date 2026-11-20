"""Cards: Markdown files with a small header, used for helpers, skills and slash commands.

    ---
    name: reviewer
    description: Reviews a change for bugs.
    tools: Read, Glob, Grep
    ---
    You are a careful code reviewer. ...

Where Cato looks (the project's folder first, then yours):
    helpers    .cato/agents/<name>.md          ~/.cato/agents/<name>.md
    skills     .cato/skills/<name>/SKILL.md    ~/.cato/skills/<name>/SKILL.md
    commands   .cato/commands/<name>.md        ~/.cato/commands/<name>.md
"""
from pathlib import Path


def read_card(path):
    """Split a card into its header (a dict) and its body (the text after the header)."""
    text = path.read_text()
    header = {}
    if text.startswith("---"):
        top, _, text = text[3:].partition("\n---")
        for line in top.strip().splitlines():
            key, _, value = line.partition(":")
            header[key.strip()] = value.strip()
    header.setdefault("name", path.parent.name if path.name == "SKILL.md" else path.stem)
    header.setdefault("description", "")
    return header, text.strip()


def find_cards(kind):
    """Every card of one kind, by name. A project card wins over yours with the same name."""
    patterns = {"agents": "*.md", "skills": "*/SKILL.md", "commands": "*.md"}
    cards = {}
    for base in (Path.home() / ".cato", Path.cwd() / ".cato"):
        for path in sorted((base / kind).glob(patterns[kind])):
            header, body = read_card(path)
            cards[header["name"]] = {**header, "body": body, "path": path}
    return cards


def skill_menu():
    """The short menu of skills that sits on the desk. The full cards stay in their files."""
    skills = find_cards("skills")
    if not skills:
        return ""
    lines = [f"- {name}: {card['description']}" for name, card in skills.items()]
    return ("Skills you can load with the Skill tool when a task matches one:\n" + "\n".join(lines))


def fill(body, arguments):
    """A command or a skill run by hand: what you typed after its name goes where $ARGUMENTS is."""
    if "$ARGUMENTS" in body:
        return body.replace("$ARGUMENTS", arguments)
    return f"{body}\n\nARGUMENTS: {arguments}" if arguments else body
