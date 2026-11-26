"""Claude Bridge for Krita: a local command server inside Krita, like the FL Studio bridge.

Listens on 127.0.0.1:47821 only. Each request is one JSON line: {"token": ..., "code": ..., "args": {...}}.
The code runs on Krita's GUI thread (Qt signals arrive there), with these names available:
    Krita, app (Krita.instance()), doc (active document or None), args, QImage, QPointF, QRect, InfoObject,
    Selection, node_by(name_or_uid), refresh()
A single expression returns its value; for statements assign the answer to `result`. print() output is returned.
The token lives in %APPDATA%\\krita\\claude_bridge_token.txt (made fresh each Krita start), so only local
programs that can read your Windows user profile can talk to it.
"""
import contextlib, io, json, os, secrets, traceback

from krita import Extension, Krita, InfoObject, Selection
from PyQt5.QtCore import QPointF, QRect, QTimer
from PyQt5.QtGui import QImage
from PyQt5.QtNetwork import QHostAddress, QTcpServer

PORT = 47821
TOKEN_FILE = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "krita", "claude_bridge_token.txt")


def _node_by(doc, key):
    if doc is None:
        raise RuntimeError("no document open")
    if key is None:
        return doc.activeNode()
    stack = list(doc.topLevelNodes())
    found = None
    while stack:
        n = stack.pop(0)
        if n.uniqueId().toString() == key or n.name() == key:
            found = n
            break
        stack.extend(n.childNodes())
    if found is None:
        raise RuntimeError("no layer named %r" % key)
    return found


def _run(code, args):
    app = Krita.instance()
    doc = app.activeDocument()

    def refresh():
        if doc is not None:
            doc.refreshProjection()
            doc.waitForDone()

    ns = {"Krita": Krita, "app": app, "doc": doc, "args": args or {}, "QImage": QImage, "QPointF": QPointF,
          "QRect": QRect, "InfoObject": InfoObject, "Selection": Selection, "refresh": refresh,
          "node_by": lambda key=None: _node_by(app.activeDocument(), key), "result": None}
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            value = eval(compile(code, "<claude>", "eval"), ns)
        except SyntaxError:
            exec(compile(code, "<claude>", "exec"), ns)
            value = ns.get("result")
    return value, out.getvalue()


class ClaudeBridge(Extension):
    def __init__(self, parent):
        super().__init__(parent)
        self.server = None
        self.token = secrets.token_hex(16)
        self.buffers = {}

    def setup(self):
        self.server = QTcpServer()
        self.server.newConnection.connect(self._accept)
        if not self.server.listen(QHostAddress.LocalHost, PORT):
            print("Claude Bridge: could not listen on port", PORT)
            return
        os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
        with open(TOKEN_FILE, "w") as f:
            f.write(self.token)

    def createActions(self, window):
        pass

    def _accept(self):
        while self.server.hasPendingConnections():
            sock = self.server.nextPendingConnection()
            self.buffers[sock] = b""
            sock.readyRead.connect(lambda s=sock: self._read(s))
            sock.disconnected.connect(lambda s=sock: self.buffers.pop(s, None))

    def _read(self, sock):
        self.buffers[sock] = self.buffers.get(sock, b"") + bytes(sock.readAll())
        if b"\n" not in self.buffers[sock]:
            return
        line, _, rest = self.buffers[sock].partition(b"\n")
        self.buffers[sock] = rest
        try:
            req = json.loads(line.decode("utf-8"))
            if req.get("token") != self.token:
                reply = {"ok": False, "error": "bad token"}
            else:
                value, printed = _run(req.get("code", ""), req.get("args"))
                json.dumps(value)  # must be JSON-able
                reply = {"ok": True, "result": value, "stdout": printed}
        except Exception as e:
            reply = {"ok": False, "error": "%s: %s" % (type(e).__name__, e), "trace": traceback.format_exc()[-1500:]}
        sock.write(json.dumps(reply).encode("utf-8") + b"\n")
        sock.flush()
        QTimer.singleShot(0, sock.disconnectFromHost)


Krita.instance().addExtension(ClaudeBridge(Krita.instance()))
