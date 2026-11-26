# Security

**What the bridge can do:** the Krita plugin runs Python code sent to it. That's how every tool works, including
`krita_exec`. It listens on **127.0.0.1 only** and requires a random token that's made fresh each time Krita
starts and saved in `%APPDATA%\krita\claude_bridge_token.txt`. So only programs running as your Windows user can
drive Krita.

- Claude Code asks before running tools unless you allowed them. Allow the `krita` tools only as far as you trust
  what you ask for.
- Nothing is sent over the internet. The optional AI tools run locally, and their models are downloaded once by
  `get_models.py`, then used offline (`HF_HUB_OFFLINE=1`).
- Turn the plugin off in Krita's Python Plugin Manager when you don't want it listening.

## Reporting a vulnerability
Please **don't open a public issue** for security problems. Use GitHub's private
[security advisory](https://github.com/xoxoFaith1993/claude-krita-bridge/security/advisories/new) form instead.
This is a volunteer project with no fixed response time.
