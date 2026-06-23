#!/usr/bin/env python3
# comment: fake eza stub for lsc tests; emits icon + colored names

# Stands in for the real `eza` binary via the EZA_BIN env var. It ignores all
# arguments and prints one entry per line, formatted like eza --oneline
# --icons=always --color=always: a leading Nerd Font icon glyph, a space, then
# the name wrapped in a green SGR sequence. (The icon is U+F086F, which lives in
# a Supplementary PUA.)
#
# Names come from the FAKE_EZA env var, newline-separated. Setting FAKE_EZA_RC
# to a non-zero value makes the stub write to stderr and exit with that code,
# so tests can confirm lsc propagates eza's own returncode unchanged.

import os
import sys

ICON = "\U000f086f"  # supplementary-PUA nerd font glyph

rc = int(os.environ.get("FAKE_EZA_RC", "0"))
if rc:
    sys.stderr.write("fake-eza: simulated failure\n")
    sys.exit(rc)

names = [n for n in os.environ.get("FAKE_EZA", "").split("\n") if n]
out = [f"{ICON} \x1b[32m{n}\x1b[0m" for n in names]
sys.stdout.write("\n".join(out) + ("\n" if out else ""))
