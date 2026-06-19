# Contributing

Thanks for your interest in lsc. It is a small, single-file tool, and the bar
for changes is mostly about keeping it that way.

## Ground rules

- No runtime dependencies. `lsc.py` must keep working with a stock Python 3.8+
  and nothing installed. `wcwidth` is used only if it happens to be importable.
- Keep it one file. The whole tool is `lsc.py`; please do not split it into a
  package unless there is a strong reason.
- Have a look at `CLAUDE.md` first. It documents the design decisions and the bugs that caused them.

## Before opening a pull request

Run the tests from the repo root:

    sh tests/run-tests.sh

If you fix a bug, add a test that fails before your change and passes after.
The tests stub `eza` through the `EZA_BIN` env var, so they need no real eza
installed.

## Style

- Filenames use hyphens, not underscores; shell scripts end in `.sh`.
- Files start with a terse `comment:` magic line near the top so `lsc` can 
  show comments about its code.
