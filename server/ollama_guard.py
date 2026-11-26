"""Watcher for the optional local AI: stops Ollama once FL Studio and Krita are both closed, then quits.

Shared by claude-fl-studio-bridge and claude-krita-bridge. Started by ollama_ctl.ensure_running() (only when a
prompt needs the local model). Rules:
  - stop Ollama when FL Studio and Krita have both been closed for the auto-stop time (default 120 s), so closing
    and quickly reopening an app, a bridge's own project switch, or the sister bridge still working never stop it;
  - only the exact Ollama process this bridge started is ever stopped (ollama_ctl.stop checks PID + start time);
  - quit once Ollama is stopped or gone. Only one copy runs at a time.
Log: guard.log in the bridge's ollama state folder (%LOCALAPPDATA%\\<bridge>\\ollama).
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ollama_ctl  # noqa: E402

POLL = 10
LOG = os.path.join(ollama_ctl.STATE_DIR, 'guard.log')


def log(msg):
    try:
        with open(LOG, 'a', encoding='utf-8') as f:
            f.write('%s  %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), msg))
    except OSError:
        pass


def main():
    grace = ollama_ctl.AUTO_STOP
    if grace <= 0 or ollama_ctl.guard_running():
        return
    os.makedirs(ollama_ctl.STATE_DIR, exist_ok=True)
    with open(ollama_ctl.GUARD_PID, 'w') as f:
        f.write(str(os.getpid()))
    log('watcher started (grace %ds)' % grace)
    closed_since = None
    started = time.time()
    try:
        while True:
            if not ollama_ctl.is_running() and time.time() - started > 60:
                log('Ollama is off -> watcher exits')
                return
            if ollama_ctl.apps_running():
                closed_since = None
            else:
                if closed_since is None:
                    closed_since = time.time()
                if ollama_ctl.restart_pending():
                    closed_since = time.time()          # the bridge's own restart: keep waiting
                elif time.time() - closed_since >= grace:
                    log('apps closed for %ds -> %s' % (grace, ollama_ctl.stop()))
                    return
            time.sleep(POLL)
    finally:
        try:
            os.remove(ollama_ctl.GUARD_PID)
        except OSError:
            pass


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        log('watcher crashed: %r' % e)
        raise
