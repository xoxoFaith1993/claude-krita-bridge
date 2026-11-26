"""krita_doctor: check every link from Claude to Krita and say, in plain words, what's wrong and how to fix it.

Order: settings -> Krita program -> plugin installed (and up to date) -> plugin switched on -> Krita running ->
port reachable -> bridge answers (token) -> document open -> optional AI tools (Python, models) ->
optional local AI (Ollama + vision model).

Run it from Claude (tool krita_doctor) or by hand:  python tools\\doctor.py [--deep]
It never starts Krita or Ollama and changes none of your settings, plugins or pictures. --deep (deep=true) also runs a short PyTorch
import in the AI tools' Python to check the GPU; that briefly uses a lot of memory, so it's off by default.
"""
import filecmp
import json
import os
import socket
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import config  # noqa: E402

OK, WARN, FAIL, SKIP = 'ok', 'warn', 'fail', 'skip'
REPO = os.path.dirname(HERE)
_BUNDLED = os.path.join(REPO, 'python', 'python.exe')
PY = _BUNDLED if os.path.isfile(_BUNDLED) else sys.executable


def cmd(script):
    """A command line that works from anywhere: this install's Python + the full script path."""
    path, _, rest = script.partition(' ')
    return '"%s" "%s"%s' % (PY, os.path.join(REPO, path), (' ' + rest) if rest else '')
CFG = config.CFG
NO_WINDOW = 0x08000000
MODELS = ('grounding-dino-base', 'sam2.1-hiera-large', 'BiRefNet', 'big-lama.pt')



def packaged_python():
    """True when this Python is a Microsoft Store / Python Install Manager (packaged) build. Those see a private copy
    of %APPDATA%, so files they write there (Krita plugin, settings) are invisible to other programs."""
    try:
        import ctypes
        n = ctypes.c_uint32(0)
        return ctypes.windll.kernel32.GetCurrentPackageFullName(ctypes.byref(n), None) != 15700   # 15700 = no package
    except Exception:
        return False


def _row(rows, name, state, detail, fix=None):
    rows.append({'check': name, 'result': state, 'detail': detail, **({'fix': fix} if fix else {})})
    return state


def krita_running():
    out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq krita.exe', '/NH'], capture_output=True, text=True,
                         creationflags=NO_WINDOW).stdout
    return 'krita.exe' in out.lower()


def plugin_dirs():
    return [os.path.join(os.environ.get('APPDATA', ''), 'krita', 'pykrita')]


def kritarc_enabled():
    rc = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'kritarc')
    try:
        lines = open(rc, encoding='utf-8', errors='replace').read().splitlines()
    except OSError:
        return None
    section = None
    for l in lines:
        if l.startswith('['):
            section = l.strip()
        elif section == '[python]' and l.strip().lower().startswith('enable_claude_bridge='):
            return l.split('=', 1)[1].strip().lower() == 'true'
    return False


def diagnose(kr=None, deep=False):
    rows = []
    _row(rows, 'settings', OK, 'config.json %s: %s' % ('found' if os.path.isfile(config.CONFIG_FILE) else
                                                       'not found (defaults in use, that is fine)', config.CONFIG_FILE))
    if packaged_python():
        _row(rows, 'Python', WARN, 'This is a Microsoft Store / Python Install Manager Python (%s). It sees a private '
             'copy of AppData, so some checks below can be wrong and files it writes there are invisible to the app.'
             % sys.executable, 'Use the Python the installer bundles (python\\python.exe in the install folder) or '
             'Python from python.org.')
    exe = CFG.get('krita_exe')
    _row(rows, 'Krita program', OK if exe and os.path.isfile(exe) else WARN, exe or 'krita.exe not found',
         None if exe and os.path.isfile(exe) else 'Only krita_launch needs it: start Krita yourself, or set "krita_exe" '
         'in %s' % config.CONFIG_FILE)

    # plugin installed / current
    ship = os.path.join(REPO, 'krita_plugin', 'claude_bridge', '__init__.py')
    found = [d for d in plugin_dirs() if os.path.isfile(os.path.join(d, 'claude_bridge', '__init__.py'))]
    if not found:
        _row(rows, 'plugin installed', WARN, 'Not in %s. (Portable Krita or a custom resource folder keeps it '
             'elsewhere; then this check cannot see it.)' % plugin_dirs()[0],
             'Close Krita and run: ' + cmd('install_plugin.py') + ' (add --resources <folder> --kritarc <file> for a '
             'portable Krita).')
    else:
        inst = os.path.join(found[0], 'claude_bridge', '__init__.py')
        same = not os.path.isfile(ship) or filecmp.cmp(inst, ship, shallow=False)
        _row(rows, 'plugin installed', OK if same else WARN, inst if same else 'Installed, but a different version '
             'from this bridge.', None if same else 'Close Krita and run: ' + cmd('install_plugin.py'))
    en = kritarc_enabled()
    _row(rows, 'plugin switched on', OK if en else WARN,
         'enable_claude_bridge=true in kritarc' if en else 'not switched on in kritarc' if en is False else 'kritarc not found',
         None if en else 'In Krita: Settings > Configure Krita > Python Plugin Manager, tick "Claude Bridge", restart Krita.')

    # Krita running, port, token
    if not krita_running():
        return _finish(rows, _row(rows, 'Krita running', FAIL, 'Krita is not open.',
                                  'Open Krita (or ask Claude: krita_launch).'))
    _row(rows, 'Krita running', OK, 'krita.exe')
    port = int(CFG['port'])
    try:
        socket.create_connection(('127.0.0.1', port), timeout=3).close()
        _row(rows, 'port %d' % port, OK, 'the plugin is listening')
    except OSError:
        return _finish(rows, _row(rows, 'port %d' % port, FAIL, 'Nothing listens on 127.0.0.1:%d, so the plugin is not '
                                  'running inside Krita.' % port,
                                  'Tick "Claude Bridge" in Settings > Configure Krita > Python Plugin Manager and restart '
                                  'Krita. If it is ticked, the manager shows its error there; or another program uses '
                                  'the port (change "port" in config.json and PORT in the plugin together).'))
    if kr is None:
        import server
        kr = server.kr
    try:
        st = kr('result = {"krita": app.version(), "docs": len(app.documents()), '
                '"active": doc.name() if doc is not None else None}', timeout=10)
        _row(rows, 'bridge answers', OK, 'Krita %s' % st.get('krita'))
        _row(rows, 'document', OK if st.get('active') else WARN,
             'active: %s' % st['active'] if st.get('active') else 'no document open (most tools need one)',
             None if st.get('active') else 'Open or create an image (krita_new / krita_open).')
    except Exception as e:
        msg = str(e).split('\n')[0]
        fix = ('Krita was restarted and the token changed; just try again.' if 'bad token' in msg else
               'Restart Krita. If it keeps failing, check the Python Plugin Manager for an error.')
        return _finish(rows, _row(rows, 'bridge answers', FAIL, msg, fix))

    _ai_tools(rows, deep)
    _local_ai(rows)
    return _finish(rows, None)


def _ai_tools(rows, deep):
    ai = CFG['ai']
    py = ai.get('python')
    if not py:
        return _row(rows, 'AI tools (optional)', SKIP, 'not set up (krita_cutout / krita_remove / krita_match need them)',
                    'Optional: see ai_tools/README.md')
    if not os.path.isfile(py):
        return _row(rows, 'AI tools (optional)', FAIL, 'ai.python points to a missing file: %s' % py,
                    'Fix "ai": {"python": ...} in %s' % config.CONFIG_FILE)
    md = ai['models_dir']
    missing = [m for m in MODELS if not os.path.exists(os.path.join(md, m))]
    _row(rows, 'AI models', WARN if missing else OK, 'missing in %s: %s' % (md, ', '.join(missing)) if missing else
         'all 4 models present in %s' % md, ('Run: "%s" ai_tools\\get_models.py "%s"' % (py, md)) if missing else None)
    if deep:
        try:
            r = subprocess.run([py, '-c', 'import torch; print(torch.__version__, torch.cuda.is_available(), '
                                'torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU")'],
                               capture_output=True, text=True, timeout=180, creationflags=NO_WINDOW)
            ok = r.returncode == 0
            _row(rows, 'AI PyTorch', OK if ok else FAIL, (r.stdout or r.stderr).strip()[-300:],
                 None if ok else 'Reinstall PyTorch for your GPU in that environment (pytorch.org).')
        except Exception as e:
            _row(rows, 'AI PyTorch', FAIL, str(e))


def _local_ai(rows):
    la = CFG['local_ai']
    if not la.get('enabled', True):
        return _row(rows, 'local AI (optional)', SKIP, 'turned off (local_ai.enabled)')
    import ollama_ctl
    st = ollama_ctl.status()
    if not st['installed'] and not st['running']:
        return _row(rows, 'local AI (optional)', SKIP, 'Ollama not installed: krita_look and the cut-out check are '
                    'skipped; everything else works.', 'Optional: install Ollama from ollama.com')
    if not st['running']:
        return _row(rows, 'local AI (optional)', OK, 'Ollama installed, not running (starts by itself when needed)'
                    if la.get('auto_start', True) else 'Ollama installed, not running (auto_start is off)')
    m = CFG['vision_model']
    have = ollama_ctl.has_model(m)
    _row(rows, 'local AI (optional)', OK if have else WARN, 'Ollama running; vision model %s %s' % (m, 'present' if have
         else 'missing'), None if have else 'Run: ollama pull %s' % m)


def _finish(rows, stopped_at):
    worst = FAIL if any(r['result'] == FAIL for r in rows) else WARN if any(r['result'] == WARN for r in rows) else OK
    out = {'summary': {OK: 'Everything checked is fine.', WARN: 'Working, with warnings (see fix lines).',
                       FAIL: 'Not working - the first failing check below is the one to fix.'}[worst], 'checks': rows}
    if stopped_at == FAIL:
        out['note'] = 'Later checks were skipped because they depend on this one.'
    return out


def text_report(res):
    sign = {OK: '[ ok ]', WARN: '[warn]', FAIL: '[FAIL]', SKIP: '[skip]'}
    lines = [res['summary'], '']
    for r in res['checks']:
        lines.append('%s %-20s %s' % (sign[r['result']], r['check'], r['detail']))
        if r.get('fix'):
            lines.append('       %-20s fix: %s' % ('', r['fix']))
    if res.get('note'):
        lines += ['', res['note']]
    return '\n'.join(lines)


if __name__ == '__main__':
    res = diagnose(deep='--deep' in sys.argv)
    print(json.dumps(res, indent=1) if '--json' in sys.argv else text_report(res))
