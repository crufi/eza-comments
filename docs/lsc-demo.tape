# comment: vhs script for the lsc demo gif (run: vhs docs/lsc-demo.tape)
#
# Prerequisites: vhs (brew install vhs), lsc and eza on PATH, and a Nerd Font
# installed. Produces docs/lsc-demo.gif with the icons/colors baked in as
# pixels, so they render for everyone (an SVG/asciinema cast would tofu the
# Nerd Font glyphs for viewers without the font).

Output lsc-demo.gif

Set Shell bash
Set FontFamily "JetBrainsMono Nerd Font Mono"
Set FontSize 20
Set Width 1080
Set Height 620
Set Padding 28
Set Theme "Dracula"
Set TypingSpeed 55ms

# ---- hidden setup: build a small sample directory ----
Hide
Type "export PS1='"
Enter
Type "$ '"
Enter
Type "rm -rf /tmp/lsc-demo && mkdir -p /tmp/lsc-demo/archive && cd /tmp/lsc-demo"
Enter
Type "printf '#!/bin/sh\n# comment: nightly rsync script\n' > backup.sh"
Enter
Type "touch report.pdf notes.md goldberg-variations.flac"
Enter
Type "mkdir -p src"
Enter
Type "lsc --set . 'a demo directory for lsc'"
Enter
Type "lsc --set report.pdf 'Q2 board deck — do not delete'"
Enter
Type "lsc --set archive 'old projects, safe to ignore'"
Enter
Type "clear"
Enter
Show

# ---- the payoff: one listing, caption + comments inline ----
Type "lsc"
Sleep 400ms
Enter
Sleep 3s

# ---- add comments live and watch them appear ----
Type "# see what each file is for at a glance:"
Enter
Sleep 100ms
Type "lsc --set notes.md 'next steps & ideas'"
Sleep 400ms
Enter
Sleep 800ms
Type "lsc"
Sleep 600ms
Enter
Sleep 2500ms
Type "# directories can have comments too"
Enter
Sleep 100ms
Type "lsc --set src 'super awesome code'"
Sleep 400ms
Enter
Sleep 800ms
Type "lsc"
Sleep 600ms
Enter
Sleep 2500ms
Type "# directory comments are shown as headers when listing that directory"
Enter
Sleep 100ms
Type "lsc src"
Sleep 400ms
Enter
Type "# comments can live in magic lines inside a file"
Enter
Sleep 500ms
Type "cat > secret_recipe <<EOF"
Enter
Type "# comment: don't tell anyone"
Enter
Enter
Type "1. put some peanut butter and some jelly on bread"
Enter
Type "2. eat"
Enter
Type "EOF"
Enter
Sleep 300ms
Type "lsc"
Enter
Sleep 5500ms

# ---- cleanup (hidden) ----
Hide
Type "cd / && rm -rf /tmp/lsc-demo"
Enter
Show
