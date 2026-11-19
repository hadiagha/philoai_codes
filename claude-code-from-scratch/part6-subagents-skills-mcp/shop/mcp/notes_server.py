"""A tiny MCP server with two tools, add_note and list_notes. Notes are kept in notes.json.

Cato starts it from .mcp.json:
    {"mcpServers": {"notes": {"command": "python3", "args": ["mcp/notes_server.py"]}}}

It reads one JSON-RPC request per line on stdin, and writes one answer per line on stdout.
It speaks MCP 2026-07-28, and still answers the older handshake for clients from before it.
"""
import json
import sys
from pathlib import Path

NOTES = Path("notes.json")

TOOLS = [
    {"name": "add_note", "description": "Save a short note for later.",
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}},
                     "required": ["text"]}},
    {"name": "list_notes", "description": "List every saved note.",
     "inputSchema": {"type": "object", "properties": {}}},
]


def call_tool(name, arguments):
    notes = json.loads(NOTES.read_text()) if NOTES.exists() else []
    if name == "add_note":
        notes.append(arguments["text"])
        NOTES.write_text(json.dumps(notes, indent=2))
        return f"Saved note {len(notes)}."
    if name == "list_notes":
        return "\n".join(f"{i}. {note}" for i, note in enumerate(notes, 1)) or "No notes yet."
    raise ValueError(f"There is no tool called {name}.")


def handle(method, params):
    if method == "server/discover":       # which versions and features this server has
        return {"supportedVersions": ["2026-07-28", "2025-11-25"], "capabilities": {"tools": {}},
                "_meta": {"io.modelcontextprotocol/serverInfo": {"name": "notes", "version": "1.0"}}}
    if method == "initialize":            # the handshake that clients from before 2026-07-28 send
        return {"protocolVersion": "2025-11-25", "capabilities": {"tools": {}},
                "serverInfo": {"name": "notes", "version": "1.0"}}
    if method == "tools/list":
        return {"tools": TOOLS, "ttlMs": 60000, "cacheScope": "private"}
    if method == "tools/call":
        try:
            text = call_tool(params["name"], params.get("arguments", {}))
            return {"content": [{"type": "text", "text": text}], "isError": False}
        except (ValueError, KeyError) as error:
            return {"content": [{"type": "text", "text": str(error)}], "isError": True}
    raise LookupError(f"Unknown method {method}")


for line in sys.stdin:
    message = json.loads(line)
    if "id" not in message:
        continue                          # a notification: no answer is sent
    try:
        answer = {"jsonrpc": "2.0", "id": message["id"],
                  "result": {"resultType": "complete", **handle(message["method"], message.get("params", {}))}}
    except LookupError as error:
        answer = {"jsonrpc": "2.0", "id": message["id"],
                  "error": {"code": -32601, "message": str(error)}}
    print(json.dumps(answer), flush=True)
