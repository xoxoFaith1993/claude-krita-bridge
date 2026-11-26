"""Settings for the Krita bridge.

Where settings come from (later wins): DEFAULTS below, auto-detection of krita.exe,
config.json in %APPDATA%\\claude-krita-bridge\\ (or the file named by KRITA_BRIDGE_CONFIG),
and the environment variable KRITA_EXE.

Run `python config.py` to print the settings in use. See config.example.json.
"""
import glob
import json
import os
import shutil

APP = 'claude-krita-bridge'
CONFIG_DIR = os.path.join(os.environ.get('APPDATA') or os.path.expanduser('~'), APP)
CONFIG_FILE = os.environ.get('KRITA_BRIDGE_CONFIG') or os.path.join(CONFIG_DIR, 'config.json')
DATA_DIR = os.path.join(os.environ.get('LOCALAPPDATA') or os.path.expanduser('~'), APP)

DEFAULTS = {
    'krita_exe': None,                       # null = auto-detect
    'port': 47821,                           # must match PORT in the Krita plugin
    'snap_dir': os.path.join(DATA_DIR, 'snaps'),
    'layer_label': 6,                        # colour label for layers Claude adds (6 = red; 0 = none)
    # optional AI tools (krita_cutout / krita_remove / krita_match), see ai_tools/README.md
    'ai': {
        'python': None,                      # python.exe of the environment with torch + transformers installed
        'models_dir': os.path.join(DATA_DIR, 'models'),
        'work_dir': os.path.join(DATA_DIR, 'work'),
        'env': {'OPENBLAS_NUM_THREADS': '4', 'OMP_NUM_THREADS': '4'},   # extra env vars, e.g. HIP_VISIBLE_DEVICES
        'timeout_seconds': 900,
    },
}


def _merge(base, extra):
    for k, v in extra.items():
        if k.startswith('_'):
            continue
        if isinstance(v, dict) and isinstance(base.get(k), dict) and k != 'env':
            _merge(base[k], v)
        else:
            base[k] = os.path.expandvars(v) if isinstance(v, str) else v


def detect_krita():
    for p in (os.environ.get('KRITA_EXE'), shutil.which('krita')):
        if p and os.path.isfile(p):
            return p
    for pattern in (r'%ProgramFiles%\Krita (x64)\bin\krita.exe', r'%ProgramFiles%\Krita*\bin\krita.exe',
                    r'%LOCALAPPDATA%\Programs\Krita*\bin\krita.exe'):
        hits = sorted(glob.glob(os.path.expandvars(pattern)))
        if hits:
            return hits[-1]
    return None


def load():
    cfg = json.loads(json.dumps(DEFAULTS))
    cfg['krita_exe'] = detect_krita()
    if os.path.isfile(CONFIG_FILE):
        with open(CONFIG_FILE, encoding='utf-8') as f:
            _merge(cfg, json.load(f))
    if os.environ.get('KRITA_EXE'):
        cfg['krita_exe'] = os.environ['KRITA_EXE']
    return cfg


CFG = load()


if __name__ == '__main__':
    print('config file: %s (%s)' % (CONFIG_FILE, 'found' if os.path.isfile(CONFIG_FILE) else 'not found, using defaults'))
    print(json.dumps(CFG, indent=1))
