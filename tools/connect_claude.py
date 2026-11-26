"""Connect this bridge to Claude Code (or undo it). Safe to run again.

  python tools\\connect_claude.py                 # register the MCP server
  python tools\\connect_claude.py --remove        # undo it
  python tools\\connect_claude.py --print         # only print what it would do

MCP server: runs `claude mcp add --scope user <name> -- <python> <server.py>` (needs the `claude` command on PATH;
otherwise it prints the command for you to run).
The Krita bridge needs no hooks (that part is for the FL Studio sister project).
"""
import argparse
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = 'krita'                          # MCP server name
SERVER = os.path.join(HERE, 'server', 'server.py')


def python_exe():
    """The bundled Python next to the install (installer), else the one running this script."""
    bundled = os.path.join(HERE, 'python', 'python.exe')
    return bundled if os.path.isfile(bundled) else sys.executable


def claude_cli():
    return shutil.which('claude') or shutil.which('claude.cmd') or shutil.which('claude.exe')


def mcp(remove, dry):
    cmd = ['mcp', 'remove', '--scope', 'user', NAME] if remove else \
        ['mcp', 'add', '--scope', 'user', NAME, '--', python_exe(), SERVER]
    cli = claude_cli()
    shown = 'claude ' + ' '.join('"%s"' % c if ' ' in c else c for c in cmd)
    if dry or not cli:
        print(('Run this to %s the MCP server:\n  ' % ('remove' if remove else 'add')) + shown)
        if not cli and not dry:
            print('(the "claude" command was not found on PATH - install Claude Code first)')
            if not remove:   # leave the command where the installer can show it
                with open(os.path.join(HERE, 'CONNECT_CLAUDE.txt'), 'w', encoding='utf-8') as f:
                    f.write('The claude command was not found, so the tools are not registered yet.\n'
                            'Install Claude Code (https://claude.com/claude-code), then run this in a terminal:\n\n  '
                            + shown + '\n\nThen start a new Claude Code session.\n')
        return
    # only ever replace or remove a registration that points at THIS copy (never someone's other install)
    cur = subprocess.run([cli, 'mcp', 'get', NAME], capture_output=True, text=True)
    exists = cur.returncode == 0 and NAME in (cur.stdout or '')
    ours = os.path.normcase(SERVER) in os.path.normcase(cur.stdout or '').replace('/', '\\')
    if exists and not ours:
        print('An MCP server named "%s" already exists and points somewhere else; leaving it alone.' % NAME)
        print('To switch to this copy, remove it first:  claude mcp remove --scope user %s' % NAME)
        return
    if remove and not exists:
        print('no MCP server "%s" registered' % NAME)
        return
    if not remove and exists:   # ours already: re-register cleanly
        subprocess.run([cli, 'mcp', 'remove', '--scope', 'user', NAME], capture_output=True)
    r = subprocess.run([cli] + cmd, capture_output=True, text=True)
    print((r.stdout or r.stderr).strip() or ('done: ' + shown))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--remove', action='store_true')
    ap.add_argument('--print', action='store_true', dest='dry')
    a = ap.parse_args()
    mcp(a.remove, a.dry)
    print('Restart Claude Code (a new session) to load the tools.')
