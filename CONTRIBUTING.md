# Contributing

Thanks for helping. This bridge is a work in progress and it's never perfect. That's why it's shared.
Artists, testers and coders are all welcome.

## Ways to help (no code needed)
- **Try it** on your Krita version and OS and file a setup report, whether it worked or not.
- **Docs:** anything that confused you is a docs bug.
- **AI tools:** report which GPU and PyTorch build worked for you.

## Reporting a bug
Use the bug report form under **Issues → New issue**, with the error text, your Krita version, and whether you
installed with Setup.exe or from source. Please don't attach pictures you don't want public.

## Code
- **Standard library only** in `server/`, and only Krita's bundled PyQt in the plugin. The AI tools may use
  PyTorch and friends, but stay optional, with a clear message when not set up.
- **New layers get the user's colour label** (`args.get("_new_label", 6)`). Never change the user's own layers
  unless asked, and keep their position and stacking when replacing one.
- **Nothing machine-specific in code:** paths and options go in `server/config.py`.
- New or changed tool: run `python tools\gen_tools_md.py`. Before a PR: `python tests\test_protocol.py` and `tests\test_doctor.py` (add a doctor check with a plain fix
  line for any new way things can break), and say
  what you tested by hand in Krita (`tests\smoke.py`).

See [ARCHITECTURE.md](ARCHITECTURE.md) for how to add a tool.

## Pull requests
Fork, branch, one topic per PR, and describe what and how you tested. By contributing, you agree your contribution
is licensed under the project's [GPL-3.0](LICENSE). Everyone follows the [Code of Conduct](CODE_OF_CONDUCT.md).
