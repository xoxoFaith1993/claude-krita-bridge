"""Offline test of the Krita bridge protocol and MCP plumbing: a fake plugin, no Krita needed.

  python tests\\test_protocol.py
"""
import io
import json
import os
import socket
import sys
import tempfile
import threading

tmp = tempfile.mkdtemp(prefix="krita-bridge-test-")
os.environ["APPDATA"] = tmp                       # token file goes to <tmp>\krita\claude_bridge_token.txt
os.makedirs(os.path.join(tmp, "krita"))
srv = socket.socket()
srv.bind(("127.0.0.1", 0))
srv.listen()
port = srv.getsockname()[1]
cfg = os.path.join(tmp, "config.json")
with open(cfg, "w") as f:
    json.dump({"port": port, "snap_dir": os.path.join(tmp, "snaps")}, f)
os.environ["KRITA_BRIDGE_CONFIG"] = cfg
with open(os.path.join(tmp, "krita", "claude_bridge_token.txt"), "w") as f:
    f.write("secret")

seen = []


def fake_plugin():
    while True:
        c, _ = srv.accept()
        buf = b""
        while b"\n" not in buf:
            buf += c.recv(65536)
        req = json.loads(buf)
        seen.append(req)
        if req["token"] != "secret":
            reply = {"ok": False, "error": "bad token"}
        elif "raise" in req["code"]:
            reply = {"ok": False, "error": "RuntimeError: boom"}
        else:
            reply = {"ok": True, "result": {"echo": req["args"]}, "stdout": ""}
        c.sendall(json.dumps(reply).encode() + b"\n")
        c.close()


threading.Thread(target=fake_plugin, daemon=True).start()
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server"))
import server as S  # noqa: E402

# 1. a call reaches the plugin with the token and args, and new-layer label is sent
r = S.kr("result = 1", x=5)
assert r["echo"]["x"] == 5 and r["echo"]["_new_label"] == 6, r
# 2. plugin errors become BridgeError
try:
    S.kr("raise RuntimeError('boom')")
    raise AssertionError("expected BridgeError")
except S.BridgeError as e:
    assert "boom" in str(e)
# 3. MCP: initialize, tools/list, tools/call
out = io.BytesIO()


class W:
    buffer = out


real = sys.stdout
sys.stdout = W()
try:
    S.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    S.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    S.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "krita_status", "arguments": {}}})
    S.handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "krita_cutout", "arguments": {"what": "cat"}}})
finally:
    sys.stdout = real
msgs = [json.loads(l) for l in out.getvalue().splitlines()]
assert msgs[0]["result"]["serverInfo"]["name"] == "krita"
names = {t["name"] for t in msgs[1]["result"]["tools"]}
assert {"krita_status", "krita_add_image", "krita_snapshot", "krita_cutout"} <= names, names
assert msgs[2]["result"]["isError"] is False
assert msgs[3]["result"]["isError"] is True and "optional" in msgs[3]["result"]["content"][0]["text"]
print("all protocol tests passed (%d tools)" % len(names))
