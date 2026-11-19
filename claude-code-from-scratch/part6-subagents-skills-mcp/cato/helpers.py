"""Helpers: subagents (the same loop, with a clean desk) and skills (recipe cards loaded on demand)."""
from .agent import run_agent
from .cards import find_cards
from .context import environment
from .tools import TOOLS, Tool

# Two helpers come built in. More can be added as cards in .cato/agents/.
BUILT_IN_HELPERS = {
    "explore": {
        "description": "Fast, read-only search. Use it to find files or code, or to answer a "
                       "question about the codebase, so the main chat stays small.",
        "tools": "Read, Glob, Grep",
        "body": "You are a search helper for Cato. Find what was asked with Glob, Grep and Read. "
                "You cannot change anything. Your report is the only thing the main session will see, "
                "so keep it under 250 words: file paths with line numbers, and the key facts. "
                "Don't paste code.",
    },
    "general": {
        "description": "Does one self-contained task with all the tools, and reports back.",
        "tools": "Read, Write, Edit, Bash, Glob, Grep",
        "body": "You are a helper working on one task for the main Cato session. "
                "Do the task, then reply with a short report of what you did and found.",
    },
}


def all_helpers():
    return {**BUILT_IN_HELPERS, **find_cards("agents")}


def run_helper(kind, task, model, settings, ask, report):
    """Run the loop again with a fresh message list. Only the final answer comes back."""
    card = all_helpers()[kind]
    names = [name.strip() for name in card.get("tools", "").split(",") if name.strip()]
    tools = [tool for tool in TOOLS if tool.name in names] if names else TOOLS
    if len(tools) < len(names):           # a typo must never mean "every tool"
        raise ValueError(f"The helper '{kind}' lists a tool Cato doesn't have: {card['tools']}.")
    messages = [{"role": "system", "content": card["body"] + "\n\n" + environment()},
                {"role": "user", "content": task}]
    answer, turns, calls = "", 0, 0
    model = card.get("model") or model   # a card can pick its own model, like a cheaper one for searching
    for event in run_agent(messages, model, tools=tools, ask=ask, settings=settings, max_turns=20):
        report(event)                    # the screen shows the helper's steps, and counts its cost
        if event["type"] == "tool_start":
            calls += 1
        elif event["type"] == "done":
            answer, turns = event["text"], event["turns"]
            if event["reason"] != "end":
                answer += f"\n(The helper stopped early: {event['reason']}.)"
    return f"{answer}\n\n(helper '{kind}': {turns} turns, {calls} tool calls)"


def helper_tools(model, settings, ask, report=lambda event: None):
    """The Agent and Skill tools. They are made per session, because they need the model and rules."""
    helpers = all_helpers()
    menu = "\n".join(f"- {name}: {card['description']}" for name, card in helpers.items())
    if "Agent" not in settings["allow"]:  # sending a helper never asks; each tool it uses still meets the gate
        settings["allow"].append("Agent")

    def agent(description, prompt, subagent_type="explore"):
        if subagent_type not in helpers:
            raise ValueError(f"No helper called {subagent_type}. Choose one of: {', '.join(helpers)}.")
        return run_helper(subagent_type, prompt, model, settings, ask, report)

    def skill(name):
        skills = find_cards("skills")
        if name not in skills:
            raise ValueError(f"No skill called {name}. Skills: {', '.join(skills) or 'none'}.")
        card = skills[name]
        return f"Skill '{name}' (folder: {card['path'].parent}):\n\n{card['body']}"

    return [
        Tool(name="Agent",
             description="Send a helper to do a task with its own clean desk. It sees only your "
                         "prompt, so say everything it needs. Only its final report comes back. "
                         f"Helpers:\n{menu}",
             parameters={"type": "object", "properties": {
                 "description": {"type": "string", "description": "3 to 5 words: what it's for."},
                 "prompt": {"type": "string", "description": "The full task for the helper."},
                 "subagent_type": {"type": "string", "description": "Which helper to send."},
             }, "required": ["description", "prompt"]},
             function=agent),
        Tool(name="Skill",
             description="Load a skill's full instructions when the task matches its description "
                         "in the skill menu.",
             parameters={"type": "object", "properties": {
                 "name": {"type": "string", "description": "The skill's name."},
             }, "required": ["name"]},
             function=skill, read_only=True),
    ]
