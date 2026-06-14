# lsc: eza listing with comments

A Python tool that runs an `eza` listing once, then annotates each file with
a short comment in an aligned column to the right of the names. Colors and
Nerd Font icons are preserved; the layout adapts to terminal width and clips
so no line ever wraps. When no file in the listing has a comment, output is
byte-identical to plain eza.

## Where comments come from

For each file, `lsc` looks for a comment in two places, in order of precedence:

1. An in-file magic line near the top of a text file, matching `comment:`
   after a comment marker. Markers recognized: `//`, `#`, `--`, `;`. The match
   is case-insensitive and tolerates leading indentation.

   (The first example below becomes the actual `lsc` comment for this `.md` file.)

       // comment: docs for my lsc (eza-with-comments) tool
       #  comment: so does this
       -- comment: and this

   Only the first 50 lines are scanned, and binary / non-UTF-8 files are
   skipped, so this is cheap and safe.

2. A per-directory manifest, `.lsc-comments.json`, mapping bare filename to
   comment. This is plain JSON content, so it syncs through iCloud and travels
   with the directory.

The magic line wins when both exist.

## Why a manifest instead of xattrs

An earlier version stored comments in a `user.comment` extended attribute.
That was dropped: iCloud sync strips non-Apple xattrs, so comments vanished on
sibling machines. The manifest is ordinary file content, so it survives iCloud
sync, file eviction, editor atomic-saves, and `rsync` to other machines. The
in-file magic line is even more durable (it is part of the file's bytes), so
it is preferred for text files; the manifest covers everything else, including
binaries where a magic line cannot live.

## Managing comments

    lsc                 list the current directory with comments
    lsc DIR             list DIR (comments resolved against DIR)
    lsc set FILE TEXT   set FILE's manifest comment
    lsc rm  FILE        remove FILE's manifest comment
    lsc get FILE        print FILE's effective comment

`set` refuses if FILE does not exist (catches typos and wrong-directory
mistakes). `set` and `rm` still act, but warn on stderr, when an in-file magic
line shadows the manifest — because the magic line is what the listing will
actually show. If the directory is read-only, `set`/`rm` print a clean error
and exit non-zero rather than crashing; listing a read-only directory is
unaffected.

## Terminal-width behavior

The listing adapts to the current terminal width:

- The name column may grow up to `NAME_FRAC` of the terminal (clamped to
  `[NAME_MIN, NAME_MAX]`), so wide terminals show longer names before
  truncating and narrow ones cut sooner.
- The comment column starts just past the longest shown name.
- Comment text is clipped with an ellipsis so the whole line fits the terminal
  and never wraps to the next row.
- When `lsc` output is piped or redirected (not a terminal), width detection
  falls back to `FALLBACK_WIDTH`, which is the right behavior — no point
  truncating to a window that isn't there.

Other display details: comment text is shown dim + italic (via
`COMMENT_STYLE`), and truncated names get a trailing ellipsis. If no file has
a comment, the listing is passed through unchanged.

## Install

    mkdir -p ~/bin
    install -m 755 lsc.py ~/bin/lsc.py

No pip packages required.

## Nerd Font (needed for icons)

eza emits Private Use Area codepoints for icons; without a Nerd Font selected
in the terminal you get tofu boxes. Install one and pick the Mono variant
(single-cell glyphs, which the alignment math assumes):

    brew install --cask font-jetbrains-mono-nerd-font

Then set the terminal font to "JetBrainsMono Nerd Font Mono". Test:

    eza --icons=always

lsc recognizes icon glyphs across all three Nerd Font PUA ranges (the BMP area
and both Supplementary areas), so any modern Nerd Font icon is stripped
correctly when resolving the filename.

## zsh functions

**Note**: in practice, I have regular `ls` alised to `lsc`.

    # hide the manifest from listings (append to any existing _eza_ignore)
    _eza_ignore=".lsc-comments.json"
    
    # interactive listing (icons auto-suppressed when piped)
    ls()      { eza --classify --icons=auto --group-directories-first --ignore-glob="$_eza_ignore" "$@"; }
    
    # listing with the aligned comment column
    lsc()     { python3 ~/bin/lsc.py "$@"; }
    
    # manage comments
    setcomm() { python3 ~/bin/lsc.py set "$@"; }
    rmcomm()  { python3 ~/bin/lsc.py rm  "$@"; }
    getcomm() { python3 ~/bin/lsc.py get "$@"; }

If `_eza_ignore` already holds globs, pipe-join instead:
`_eza_ignore="$_eza_ignore|.lsc-comments.json"`.

## Usage

    setcomm runcpp.sh "compile+run wrapper with magic-comment flags"
    setcomm archive.zip "Q2 board deck, do not delete"
    lsc                 # current directory
    lsc ~/bin           # another directory, from anywhere

Directory argument support: `lsc DIR` resolves names against DIR, so comment
lookups work even when run from a different working directory. This covers the
single-directory case only. Multiple paths, file arguments, or globs fall back
to current-directory name resolution, because eza's --oneline output does not
record which directory each line came from.

## Tunables (top of lsc.py)

    MANIFEST_NAME  = ".lsc-comments.json"  # per-directory comment store
    NAME_FRAC      = 0.5     # max share of terminal width for the name column
    NAME_MIN       = 20      # never truncate names shorter than this
    NAME_MAX       = 60      # never let the name column grow past this
    GAP            = 2       # gap between names and the comment column
    FALLBACK_WIDTH = 80      # width used when output is piped (no tty)
    COMMENT_STYLE  = "2;3"   # ANSI SGR for comments: 2=dim, 3=italic; "" = plain

To pin the column instead of letting it shift as you resize, set `NAME_MIN`
and `NAME_MAX` close together (e.g. both near 38).

## Notes and caveats

- The manifest is keyed by bare filename and lives in the directory, so it
  travels when you move the folder. Renaming a file leaves its entry stale
  (harmless — it just stops matching). There is no `mv` subcommand yet to
  rename a key alongside a file.
- Width is counted by codepoint, correct for ASCII names and single-cell Nerd
  Font glyphs. Install `wcwidth` (`pip install wcwidth`) for exact alignment
  with wide CJK or emoji filenames; the script uses it automatically if present.
- The manifest is written atomically (temp file + rename) so an interrupted
  write cannot corrupt it. A failed write (read-only directory) leaves no
  orphaned temp file. An emptied manifest deletes its file rather than leaving
  an empty JSON object.
- The interactive `ls` uses `--icons=auto`; `lsc` forces `--icons=always`
  internally because it pipes eza but still wants glyphs rendered.

## Minor missing features

- A `mv` subcommand to move a manifest entry when a file is renamed. (But in practice, I prefer inline text comments anyway.)
- Multi-directory arguments (`lsc dir1 dir2`) would need parsing eza's section
  headers to know which directory each name belongs to.
- Surviving into `eza -l` long-format output would need rework, since long
  format puts the name at the end of a metadata row.
