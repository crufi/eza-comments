# comment: vhs script for the lsc demo gif (run: vhs docs/lsc-demo.tape)
#
# Prerequisites: vhs (brew install vhs), lsc and eza on PATH, and a Nerd Font
# installed. Produces docs/lsc-demo.gif with the icons/colors baked in as
# pixels, so they render for everyone (an SVG/asciinema cast would tofu the
# Nerd Font glyphs for viewers without the font).
#
# Build animgif with: vhs lsc-demo.tape && code lsc-demo.gif

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
Type "touch report.pdf notes.md bwv_565.flac"
Enter
Type "mkdir -p src && touch src/hello.cpp src/hello.h src/README.md"
Enter
Type "lsc --set . 'a demo directory for lsc'"
Enter
Type "lsc --set report.pdf 'Q2 board deck — do not delete'"
Enter
Type "lsc --set archive 'old projects, safe to ignore'"
Enter
Type "export LSC_HILITE_SECS=5" # otherwise every file above would be hilighted
Enter
Type "clear"
Enter
Sleep 5s
Show

# ---- the payoff: one listing, caption + comments inline ----
Sleep 400ms
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
Type "# directories can have comments too (new comments are hilighted):"
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
Type "# directory comments are shown as headers when listing that directory:"
Enter
Sleep 100ms
Type "lsc src"
Sleep 400ms
Enter
Sleep 2s
Type "# comments can live in magic lines inside a file:"
Enter
Sleep 500ms
Type "cat > secret_recipe <<EOF"
Enter
Enter
Type "    # comment: TOP SECRET - don't tell anyone!!!"
Sleep 500ms
Enter
Enter
Type "    1. put peanut butter and jelly on bread"
Enter
Type "    2. eat"
Enter
Sleep 200ms
Type "EOF"
Enter
Sleep 500ms
Type "lsc"
Enter
Sleep 11s

# ---- cleanup (hidden) ----
Hide
Type "cd / && rm -rf /tmp/lsc-demo"
Enter
Show
