# Build a Claude Code Clone From Scratch: the code

The code for the PhiloAI series *Build a Claude Code Clone From Scratch*. We build **Cato**, a Claude Code clone in plain Python, one part per video. Each part adds one box to the same system: tools, a real terminal, permissions, memory and helpers, around the loop from Part 1. Each part is a complete, runnable copy, and the difference between two parts is exactly what that video adds.

Cato is named after Cato the Younger, a Roman known for logic and for sticking to the rules.

| Folder | Video | What Cato gains |
|---|---|---|
| [`part1-agent-loop/`](part1-agent-loop/) | Part 1: The Agent Loop | the core: a model, one shell tool, the loop, and a yes/no before each command |
| [`part2-tools/`](part2-tools/) | Part 2: Tools That Read and Edit Code | six tools (Read, Write, Edit, Bash, Glob, Grep), one path for every call, and edits that read first, match exactly and match once |
| [`part3-terminal/`](part3-terminal/) | Part 3: A Terminal Like Claude Code | a real screen: the answer streams in, the loop hands out events, headless mode, Ctrl+C that keeps your chat, a cost limit, and record and replay |

New parts are added here as each video comes out.

Cato talks to models through [OpenRouter](https://openrouter.ai), so one key works with many models. This is an independent educational project, not affiliated with or endorsed by Anthropic.
