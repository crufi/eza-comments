# comment: shell functions for lsc; source from your shell rc (bash or zsh)

# Hide the manifest from listings, merging with any existing _eza_ignore.
if [ -n "$_eza_ignore" ]; then
  _eza_ignore="$_eza_ignore|.lsc-comments.json"
else
  _eza_ignore=".lsc-comments.json"
fi

# `lsc` itself is the installed command (make install puts it on PATH), so it
# needs no wrapper. To use the comment column for every listing, alias ls to it:
#   alias ls=lsc

# Manage comments.
setcomm() { lsc --set "$@"; }
rmcomm()  { lsc --rm  "$@"; }
getcomm() { lsc --get "$@"; }
