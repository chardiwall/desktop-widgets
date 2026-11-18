#!/usr/bin/python3
"""Send a Python file (or -c code) to the running Blender via the MCP for Blender add-on (127.0.0.1:9876)."""
import json, socket, sys

def run(code, timeout=600):
    s = socket.create_connection(("127.0.0.1", 9876), timeout=timeout)
    s.sendall(json.dumps({"type": "execute_code", "params": {"code": code}}).encode())
    buf = b""
    while True:
        chunk = s.recv(1 << 20)
        if not chunk:
            break
        buf += chunk
        try:
            return json.loads(buf)
        except json.JSONDecodeError:
            continue
    return json.loads(buf)

if __name__ == "__main__":
    code = sys.argv[2] if sys.argv[1] == "-c" else open(sys.argv[1]).read()
    r = run(code)
    res = r.get("result", r)
    print(r.get("status"), "|", res.get("result", res) if isinstance(res, dict) else res)
