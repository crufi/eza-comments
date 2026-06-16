#!/bin/sh
# comment: run the lsc regression tests

here="$(cd "$(dirname "$0")" && pwd)"
chmod +x "$here/fake-eza.py"
exec python3 "$here/test-lsc.py"
