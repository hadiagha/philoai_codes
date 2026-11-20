"""MCP: other programs that offer tools. Cato starts them and talks through their stdin and stdout.

Each message is one line of JSON-RPC 2.0: a numbered request, and an answer with the same number.
    -> {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {"_meta": {...}}}
    <- {"jsonrpc": "2.0", "id": 2, "result": {"resultType": "complete", "tools": [...]}}

Cato speaks MCP 2026-07-28: there is no handshake, and every request says which version it speaks.
Older servers (2025-11-25 and before) want a handshake first, so Cato falls back to that.

Servers are listed in .mcp.json in the project, like Claude Code:
    {"mcpServers": {"time": {"command": "uvx", "args": ["mcp-server-time"]}}}
"""
import json
import os
import select
import subprocess
from pathlib import Path

from . import __version__
from .tools import Tool

VERSION = "2026-07-28"     # the MCP revision Cato speaks
LEGACY = "2025-11-25"      # the last revision with a handshake, for older servers
WAIT = 30                  # seconds to wait for an answer before giving up


def send(server, message):
    """One message is one line of JSON."""
    server["process"].stdin.write((json.dumps(message) + "\n").encode())
    server["process"].stdin.flush()


def read_message(server, wait=WAIT):
    """The server's next line, as a dict. A server that stays quiet for `wait` seconds is stuck."""
    while True:
        while b"\n" not in server["buffer"]:
            ready, _, _ = select.select([server["process"].stdout], [], [], wait)
            if not ready:
                raise TimeoutError(f"The MCP server '{server['name']}' didn't answer in {wait} s.")
            chunk = os.read(server["process"].stdout.fileno(), 65536)
            if not chunk:
                raise RuntimeError(f"The MCP server '{server['name']}' stopped.")
            server["buffer"] += chunk
        line, _, server["buffer"] = server["buffer"].partition(b"\n")
        if line.strip():
            return json.loads(line)


def request(server, method, params=None, wait=WAIT):
    """Send a numbered request and wait for the answer with the same number."""
    server["next_id"] += 1
    number = server["next_id"]
    params = dict(params or {})
    if server["version"] == VERSION:      # every request says who's asking, and in which version
        params["_meta"] = {"io.modelcontextprotocol/protocolVersion": VERSION,
                           "io.modelcontextprotocol/clientInfo": {"name": "cato", "version": __version__},
                           "io.modelcontextprotocol/clientCapabilities": {}}
    send(server, {"jsonrpc": "2.0", "id": number, "method": method, "params": params})
    while True:
        message = read_message(server, wait)
        if message.get("id") == number:
            if "error" in message:
                raise RuntimeError(message["error"].get("message", "MCP error"))
            return message["result"]
        # anything else is a notification, like progress on a long call: skip it


def start_server(name, config):
    """Start the program, then ask it which versions it speaks. An older one gets the handshake."""
    process = subprocess.Popen([config["command"], *config.get("args", [])], bufsize=0,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                               env={**os.environ, **config.get("env", {})})
    server = {"name": name, "process": process, "next_id": 0, "buffer": b"", "version": VERSION}
    try:
        found = request(server, "server/discover", wait=10)
        if VERSION not in found.get("supportedVersions", []):
            raise RuntimeError(f"it speaks {', '.join(found.get('supportedVersions', []))}, not {VERSION}")
    except (RuntimeError, TimeoutError):
        if process.poll() is not None:
            raise RuntimeError(f"The MCP server '{name}' stopped.")
        server["version"] = LEGACY        # an older server: shake hands first, then talk
        request(server, "initialize", {"protocolVersion": LEGACY, "capabilities": {},
                                       "clientInfo": {"name": "cato", "version": __version__}})
        send(server, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    return server


def tool_caller(server, tool_name):
    """A Python function that runs one of the server's tools."""
    def call(**arguments):
        result = request(server, "tools/call", {"name": tool_name, "arguments": arguments})
        if result.get("resultType") == "input_required":
            raise ValueError("This tool needs more input from you, and Cato can't ask for it yet.")
        text = "\n".join(item.get("text", f"[{item.get('type')}]") for item in result.get("content", []))
        if result.get("isError"):
            raise ValueError(text)
        return text or "(no output)"
    return call


def server_tools(server):
    """The server's tools, as ordinary Cato tools named mcp__<server>__<tool>."""
    specs, cursor = [], None
    while True:                           # a long list can come in pages
        page = request(server, "tools/list", {"cursor": cursor} if cursor else {})
        specs += page.get("tools", [])
        cursor = page.get("nextCursor")
        if not cursor:
            break
    return [Tool(name=f"mcp__{server['name']}__{spec['name']}",
                 description=spec.get("description", ""),
                 parameters=spec.get("inputSchema") or {"type": "object", "properties": {}},
                 function=tool_caller(server, spec["name"]),
                 read_only=False)         # a server's own "read-only" label is not proof: always check
            for spec in specs]


def load_servers(approve=lambda name, config: True):
    """Start every server in .mcp.json that you approve. Returns (servers, their tools, problems)."""
    path = Path.cwd() / ".mcp.json"
    servers, tools, problems = [], [], []
    if not path.exists():
        return servers, tools, problems
    for name, config in json.loads(path.read_text()).get("mcpServers", {}).items():
        if not approve(name, config):     # starting a server runs a program on your machine: you decide
            problems.append(f"{name}: not started")
            continue
        try:
            server = start_server(name, config)
            servers.append(server)
            tools += server_tools(server)
        except (OSError, RuntimeError, json.JSONDecodeError) as error:
            problems.append(f"{name}: {error}")
    return servers, tools, problems


def stop_servers(servers):
    """Close each server's input, the polite way to say goodbye. Force it if it doesn't leave."""
    for server in servers:
        try:
            server["process"].stdin.close()
            server["process"].wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            server["process"].kill()
