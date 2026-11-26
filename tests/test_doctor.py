"""Offline tests for krita_doctor: fake Krita / port / plugin states, no Krita or Ollama needed.

  python tests\\test_doctor.py
"""
import os
import socket
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'server'))
import config  # noqa: E402
import doctor  # noqa: E402

config.CFG['local_ai']['enabled'] = False
config.CFG['ai']['python'] = None


def result(res, name):
    return next(r for r in res['checks'] if r['check'].startswith(name))


# 1. Krita closed -> stops at "Krita running" with a fix
doctor.krita_running = lambda: False
r = doctor.diagnose(kr=lambda *a, **k: {})
assert result(r, 'Krita running')['result'] == 'fail' and 'fix' in result(r, 'Krita running')

# 2. Krita open but nothing on the port -> plugin advice
doctor.krita_running = lambda: True
config.CFG['port'] = 1          # nothing listens there
r = doctor.diagnose(kr=lambda *a, **k: {})
assert result(r, 'port')['result'] == 'fail' and 'Python Plugin Manager' in result(r, 'port')['fix']

# 3. port open, bridge answers, document open -> ok rows, AI tools skipped
srv = socket.socket()
srv.bind(('127.0.0.1', 0))
srv.listen()
config.CFG['port'] = srv.getsockname()[1]
r = doctor.diagnose(kr=lambda *a, **k: {'krita': '5.3.0', 'docs': 1, 'active': 'test.kra'})
assert result(r, 'bridge answers')['result'] == 'ok' and result(r, 'document')['result'] == 'ok'
assert result(r, 'AI tools')['result'] == 'skip'

# 4. bad token -> "try again"
def bad(*a, **k):
    raise RuntimeError('bad token')
r = doctor.diagnose(kr=bad)
assert 'try again' in result(r, 'bridge answers')['fix']
assert 'fix:' in doctor.text_report(r)
print('all doctor tests passed')
