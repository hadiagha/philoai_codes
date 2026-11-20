# Build a Claude Code Clone From Scratch: the code

The code for the PhiloAI series *Build a Claude Code Clone From Scratch*. We build **Cato**, a Claude Code clone in plain Python, one part per video. Each part adds one box to the same system: tools, a real terminal, permissions, memory and helpers, around the loop from Part 1. Each part is a complete, runnable copy, and the difference between two parts is exactly what that video adds.

Cato is named after Cato the Younger, a Roman known for logic and for sticking to the rules.

| Folder | Video | What Cato gains |
|---|---|---|
| [`part1-agent-loop/`](part1-agent-loop/) | Part 1: The Agent Loop | the core: a model, one shell tool, the loop, and a yes/no before each command |
| [`part2-tools/`](part2-tools/) | Part 2: Tools That Read and Edit Code | six tools (Read, Write, Edit, Bash, Glob, Grep), one path for every call, and edits that read first, match exactly and match once |
| [`part3-terminal/`](part3-terminal/) | Part 3: A Terminal Like Claude Code | a real screen: the answer streams in, the loop hands out events, headless mode, Ctrl+C that keeps your chat, a cost limit, and record and replay |
| [`part4-permissions/`](part4-permissions/) | Part 4: Permissions and Hooks | a gate before every tool: allow, ask or deny rules that read each piece of a command, hooks before and after a tool, four modes including plan mode, and reads side by side |
| [`part5-memory/`](part5-memory/) | Part 5: Memory and Context | a desk it can measure and clear: `/context`, notes in `CATO.md` read folder by folder, the reread discount (prompt caching), big output saved to a file, old results cleared, and `/compact` |
| [`part6-subagents-skills-mcp/`](part6-subagents-skills-mcp/) | Part 6: Subagents, Skills and MCP | help, through the same tool list: helpers that work on a desk of their own and send back only a report, skills loaded from a short menu when a task needs them, slash commands, and tools from other programs over MCP |
| [`part7-how-it-connects/`](part7-how-it-connects/) | Part 7: How It All Connects | no new code: one real request traced through every function (398 of them, in 11 files), and a small test of Cato against the real Claude Code on eight tasks |

The series is complete: Cato v0.6 is the whole system.

Cato talks to models through [OpenRouter](https://openrouter.ai), so one key works with many models. This is an independent educational project, not affiliated with or endorsed by Anthropic.
