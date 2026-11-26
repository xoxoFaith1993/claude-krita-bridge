"""Check the whole Krita bridge setup and print what's wrong and how to fix it. Changes nothing.

  python tools\\doctor.py           # plain report
  python tools\\doctor.py --deep    # also test the AI tools' PyTorch (briefly uses a lot of memory)
  python tools\\doctor.py --json    # as JSON (check it for private paths before posting it anywhere)
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'server'))
import doctor  # noqa: E402

if __name__ == '__main__':
    res = doctor.diagnose(deep='--deep' in sys.argv)
    print(json.dumps(res, indent=1) if '--json' in sys.argv else doctor.text_report(res))
    sys.exit(1 if any(r['result'] == 'fail' for r in res['checks']) else 0)
