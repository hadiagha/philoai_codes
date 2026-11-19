"""An older MCP server (2025-11-25): it wants the handshake before anything else. For the wire demo."""
import json, sys
ready = False
for line in sys.stdin:
    m = json.loads(line)
    if "id" not in m:
        ready = ready or m["method"] == "notifications/initialized"
        continue
    if m["method"] == "initialize":
        out = {"protocolVersion": "2025-11-25", "capabilities": {"tools": {}}}
    elif ready and m["method"] == "tools/list":
        out = {"tools": [{"name": "ping", "inputSchema": {"type": "object"}}]}
    elif ready and m["method"] == "tools/call":
        out = {"content": [{"type": "text", "text": "pong"}]}
    else:
        print(json.dumps({"jsonrpc": "2.0", "id": m["id"], "error": {"code": -32601, "message": "no"}}), flush=True)
        continue
    print(json.dumps({"jsonrpc": "2.0", "id": m["id"], "result": out}), flush=True)
