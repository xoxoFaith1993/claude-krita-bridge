"""Regenerate docs/TOOLS.md from the tool table in server/server.py (run after adding or changing a tool).

  python tools\\gen_tools_md.py          # write docs/TOOLS.md
  python tools\\gen_tools_md.py --check  # exit 1 if docs/TOOLS.md is out of date (used before releases)
"""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, 'server'))
import server  # noqa: E402

OUT = os.path.join(HERE, 'docs', 'TOOLS.md')


def arg_list(props, req):
    out = []
    for k, v in props.items():
        t = v.get('type', '')
        t = '/'.join(t) if isinstance(t, list) else t
        if 'enum' in v:
            t = ' \\| '.join(str(e) for e in v['enum'])
        out.append(('**%s**' if k in req else '%s') % k + (' (%s)' % t if t else ''))
    return ', '.join(out) or '-'


def build():
    lines = ['# Tools', '',
             'Generated from `server/server.py` by `tools/gen_tools_md.py` (%d tools). Required arguments are in **bold**.'
             % len(server.TOOLS), '',
             'Layers are found by name or uid; the default is the active layer.', '',
             '| Tool | Arguments | What it does |', '|---|---|---|']
    for name, desc, props, req, _ in server.TOOLS:
        quiet = ''
        lines.append('| `%s`%s | %s | %s |' % (name, quiet, arg_list(props, req), desc.replace('|', '\\|')))
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    text = build()
    if '--check' in sys.argv:
        cur = open(OUT, encoding='utf-8').read() if os.path.exists(OUT) else ''
        print('docs/TOOLS.md is up to date' if cur == text else 'docs/TOOLS.md is OUT OF DATE: run tools\\gen_tools_md.py')
        sys.exit(0 if cur == text else 1)
    with open(OUT, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    print('wrote', OUT, '(%d tools)' % len(server.TOOLS))
