# comment: shell functions for lsc; source from your shell rc (bash or zsh)
#
# This file is meant to be sourced (not run). The active lines below set up
# `_eza_ignore`, the convenience wrappers, and nothing else. Everything that is
# commented out is an opt-in: a knob you can uncomment to change behavior. The
# defaults shown beside each one are lsc's built-in defaults, so an uncommented
# line only matters when you change the value.

# ----- hide the manifest from listings ---------------------------------------
# Merge lsc's manifest filename into any existing _eza_ignore so an eza-based
# `ls` doesn't show the .lsc-comments.json sidecar.

if [ -n "$_eza_ignore" ]; then
  _eza_ignore="$_eza_ignore|.lsc-comments.json"
else
  _eza_ignore=".lsc-comments.json"
fi

# ----- using lsc as your default listing -------------------------------------
# `lsc` itself is the installed command (make install copies it to BINDIR,
# defaulted to ~/.local/bin but overrideable with `PREFIX=...`, and warns if
# that isn't on your PATH), so it needs no wrapper. To use the comment column
# for every listing, alias `ls` to it:

#alias ls=lsc

# ----- convenience wrappers --------------------------------------------------
# Thin shortcuts around the manifest-management flags.

setcomm() { lsc --set "$@"; }
rmcomm()  { lsc --rm  "$@"; }
getcomm() { lsc --get "$@"; }

# ----- environment overrides (all optional) ----------------------------------
# Uncomment and edit any of these to change lsc's behavior without touching
# lsc.py. The value shown is the built-in default.

# eza flags. lsc passes these by default; set LSC_EZA_OPTS to change them,
# writing flags as if straight to eza. A flag whose option is already a default
# replaces it in place (aliases included, e.g. --colour, -F); anything else is
# appended. --oneline is always forced and cannot be overridden. Dropping
# --no-quotes makes comments disappear on filenames containing spaces.
#export LSC_EZA_OPTS="--color=always --icons=always --no-quotes --classify --group-directories-first"
#export LSC_EZA_OPTS="--icons=never"                 # no Nerd Font? turn icons off
#export LSC_EZA_OPTS="--icons=always --sort=size --git"

# Read iCloud-evicted ("Optimize Mac Storage") files too. By default lsc skips
# the magic-comment probe on dataless files so a listing never forces a
# download; set to 1 to read them anyway (accepting the downloads and delay).
# Equivalent to passing --fetch-icloud / --fetch per run. No-op off macOS.
#export LSC_FETCH_ICLOUD=0

# Recency highlight: a comment changed within LSC_HILITE_SECS is drawn in
# LSC_HILITE_STYLE instead of the usual comment style, so a just-set comment
# stands out. On by default; set LSC_HILITE_RECENT=0 to turn it off (a per-run
# --hilite-recent / --no-hilite-recent flag overrides either way).
#export LSC_HILITE_RECENT=1

# ANSI SGR for comment text: 2=dim, 3=italic. Empty string = plain text.
#export LSC_COMMENT_STYLE="2;3"

# ANSI SGR for a recently-changed comment (default is a muted gold).
#export LSC_HILITE_STYLE="38;5;179"

# How many seconds counts as "recently changed" for the highlight above.
#export LSC_HILITE_SECS=60

# Test-only: pin lsc's idea of "now" to a fixed ISO-8601 local timestamp so the
# recency highlight is deterministic. Leave unset in normal use.
#export LSC_NOW="2026-06-23T14:05:00-07:00"
