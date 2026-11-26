"""Optional local AI (Ollama): start it only when a tool needs it, and stop it again after the app closes.

Shared by the sister projects claude-fl-studio-bridge and claude-krita-bridge (same file in both).

- ensure_running(): if Ollama isn't answering and "local_ai.auto_start" is on, start `ollama serve` hidden on the
  address in "ollama_host", wait for it, and start the watcher (ollama_guard.py). Never raises.
- The watcher stops Ollama once FL Studio AND Krita have both been closed for the auto-stop time (default 120 s;
  0 = never), so the two bridges never stop an Ollama the other one still uses - and ONLY if this bridge started
  that exact process (its PID and start time are recorded). An Ollama you started yourself, or that runs at login,
  is never stopped. If some other app uses an Ollama the bridge started, set auto-stop to 0.
Nothing here runs at login or when you open the app yourself: only when a prompt needs the local model.
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402

_CFG = getattr(config, 'CFG', None) or {}
LA = _CFG.get('local_ai') or {}
AUTO_STOP = int(LA.get('auto_stop_after_app_closed_seconds', LA.get('auto_stop_after_fl_closed_seconds', 120)) or 0)
WATCHED_APPS = ('FL64.exe', 'krita.exe')     # the watcher waits until all of these are closed


def normalize_host(h):
    """'0.0.0.0:11434' / '127.0.0.1:11434' / 'http://host:port/' -> 'http://host:port' (as Ollama's own OLLAMA_HOST)."""
    h = str(h or '').strip() or 'http://localhost:11434'
    if '://' not in h:
        h = 'http://' + h
    scheme, rest = h.split('://', 1)
    rest = rest.rstrip('/')
    if rest.startswith('0.0.0.0'):
        rest = '127.0.0.1' + rest[len('0.0.0.0'):]
    if ':' not in rest.split(']')[-1]:
        rest += ':11434'
    return scheme + '://' + rest


OLLAMA = normalize_host(_CFG.get('ollama_host') or os.environ.get('OLLAMA_HOST'))
HOSTPORT = OLLAMA.split('://', 1)[1]
STATE_DIR = os.path.join(config.DATA_DIR, 'ollama')
STARTED_BY_US = os.path.join(STATE_DIR, 'started_by_bridge.pid')
GUARD_PID = os.path.join(STATE_DIR, 'guard.pid')
FLAG = os.path.join(STATE_DIR, 'app_restarting.flag')
GUARD = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ollama_guard.py')
CREATE_NO_WINDOW, DETACHED = 0x08000000, 0x00000008


def _get(path, timeout=2):
    with urllib.request.urlopen(OLLAMA + path, timeout=timeout) as r:
        return json.load(r)


def is_running():
    try:
        _get('/api/version', 1)
        return True
    except Exception:
        return False


def is_local():
    host = HOSTPORT.rsplit(':', 1)[0].strip('[]').lower()
    return host in ('localhost', '127.0.0.1', '::1')


def ollama_exe():
    exe = LA.get('ollama_exe')
    if exe and os.path.isfile(exe):
        return exe
    for p in (shutil.which('ollama'),
              os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'Ollama', 'ollama.exe'),
              os.path.join(os.environ.get('ProgramFiles', ''), 'Ollama', 'ollama.exe')):
        if p and os.path.isfile(p):
            return p
    return None


def models():
    """Names of the models pulled into Ollama (empty if it isn't running)."""
    try:
        return [m['name'] for m in _get('/api/tags').get('models', [])]
    except Exception:
        return []


def has_model(name):
    return any(m == name or m.split(':')[0] == name or m == name + ':latest' for m in models())


# ---------------------------------------------------------------- processes
def _image_of(pid):
    out = subprocess.run(['tasklist', '/FI', 'PID eq %d' % pid, '/FO', 'CSV', '/NH'], capture_output=True, text=True,
                         creationflags=CREATE_NO_WINDOW).stdout
    for line in out.splitlines():
        cols = [c.strip('"') for c in line.split('","')]
        if len(cols) > 1 and cols[1] == str(pid):
            return cols[0].lower()
    return None


def _start_time(pid):
    """Process creation time (FILETIME as int), or None. Tells a reused PID from the original process."""
    k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    k32.OpenProcess.restype = wt.HANDLE
    h = k32.OpenProcess(0x1000, False, pid)          # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return None
    try:
        c, e, k, u = wt.FILETIME(), wt.FILETIME(), wt.FILETIME(), wt.FILETIME()
        if not k32.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(k), ctypes.byref(u)):
            return None
        return (c.dwHighDateTime << 32) | c.dwLowDateTime
    finally:
        k32.CloseHandle(h)


def apps_running():
    out = subprocess.run(['tasklist', '/FO', 'CSV', '/NH'], capture_output=True, text=True,
                         creationflags=CREATE_NO_WINDOW).stdout.lower()
    return [a for a in WATCHED_APPS if '"%s"' % a.lower() in out]


def guard_running():
    try:
        with open(GUARD_PID) as f:
            pid = int(f.read().strip())
    except (OSError, ValueError):
        return False
    return (_image_of(pid) or '').startswith('python')


def start_guard():
    if guard_running() or AUTO_STOP <= 0:
        return False
    py = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
    subprocess.Popen([py if os.path.exists(py) else sys.executable, GUARD], creationflags=CREATE_NO_WINDOW | DETACHED,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    return True


def _record():
    try:
        with open(STARTED_BY_US) as f:
            parts = f.read().split()
        return int(parts[0]), (int(parts[1]) if len(parts) > 1 else None)
    except (OSError, ValueError, IndexError):
        return None, None


def started_by_us(cleanup=True):
    """True only if the process this bridge started is still that same ollama.exe: same PID, image and start
    time (a PID reused after a crash or reboot - even by another ollama.exe - doesn't count)."""
    pid, t0 = _record()
    if pid is None:
        return False
    if _image_of(pid) == 'ollama.exe' and t0 is not None and _start_time(pid) == t0:
        return True
    if cleanup:
        try:
            os.remove(STARTED_BY_US)
        except OSError:
            pass
    return False


def ensure_running(wait=30):
    """True if Ollama answers (starting it if allowed). Never raises."""
    try:
        if is_running():
            if started_by_us(cleanup=False):
                start_guard()                 # e.g. it came up after an earlier wait ran out
            return True
        if not LA.get('enabled', True) or not LA.get('auto_start', True) or not is_local():
            return False                      # turned off, or ollama_host is another machine: nothing to start here
        exe = ollama_exe()
        if not exe:
            return False
        env = dict(os.environ, OLLAMA_HOST=HOSTPORT, **{k: str(v) for k, v in (LA.get('serve_env') or {}).items()})
        p = subprocess.Popen([exe, 'serve'], env=env, creationflags=CREATE_NO_WINDOW | DETACHED,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(STARTED_BY_US, 'w') as f:
            f.write('%d %s' % (p.pid, _start_time(p.pid) or ''))
        end = time.time() + wait
        while time.time() < end:
            if is_running():
                start_guard()
                return True
            time.sleep(0.5)
        start_guard()                         # still starting: the watcher will stop it later if needed
        return False
    except Exception:
        return False


def stop():
    """Unload models and stop the Ollama server - only the exact process this bridge started."""
    if not started_by_us():
        return {'stopped': False, 'why': 'Ollama was not started by the bridge, so it is left running'}
    try:
        loaded = [m['name'] for m in _get('/api/ps').get('models', [])]
    except Exception:
        loaded = []
    for name in loaded:
        try:
            req = urllib.request.Request(OLLAMA + '/api/generate', json.dumps({'model': name, 'keep_alive': 0}).encode(),
                                         {'Content-Type': 'application/json'})
            urllib.request.urlopen(req, timeout=20).read()
        except Exception:
            pass
    pid, _ = _record()
    r = subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'], capture_output=True, text=True,
                       creationflags=CREATE_NO_WINDOW)
    try:
        os.remove(STARTED_BY_US)
    except OSError:
        pass
    return {'stopped': r.returncode == 0}


def mark_fl_restart(seconds=180):
    """Tell the watcher that the app is about to close on purpose and will come back (FL project switches)."""
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(FLAG, 'w') as f:
            f.write(str(time.time() + seconds))
    except OSError:
        pass


def restart_pending():
    try:
        with open(FLAG) as f:
            return time.time() < float(f.read().strip())
    except (OSError, ValueError):
        return False


def status():
    """Read-only summary (deletes nothing, starts nothing)."""
    return {'installed': bool(ollama_exe()), 'running': is_running(), 'started_by_bridge': started_by_us(cleanup=False),
            'models': models(), 'watcher_running': guard_running(), 'host': OLLAMA}


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'status'
    if cmd == 'start':
        print('running' if ensure_running() else 'could not start (is Ollama installed? local_ai.auto_start on?)')
    elif cmd == 'stop':
        print(stop())
    else:
        print(json.dumps(status(), indent=1))
