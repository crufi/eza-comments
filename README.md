# lsc: eza listing with comments

[![tests](https://github.com/crufi/eza-comments/actions/workflows/test.yaml/badge.svg)](https://github.com/crufi/eza-comments/actions/workflows/test.yaml)

> A single-file Python wrapper that adds an aligned, per-file comment column to basic
> [`eza`](https://github.com/eza-community/eza) output — colors and Nerd Font icons intact. No dependencies.

A Python tool that runs `eza` once, annotating file with
a short comment in an aligned column to the right of the names. Colors and
Nerd Font icons are preserved; the layout adapts to terminal width and clips
so no line ever wraps. When no file in the listing has a comment, output reduces to plain `eza`. All non-`lsc`-specific flags are passed thru to `eza`.

![lsc screenshot demo](docs/lsc-demo.gif)

Requirements: Python 3.8+ (uses the walrus operator), [`eza`](https://github.com/eza-community/eza),
and a Nerd Font for icons if desired (see below). `wcwidth` is used if importable but is
not required.

## Prior art

The idea of per-file descriptions in a listing isn't new; this implementation is
inspired by the original Macintosh Finder (Horn and Capps, 1984). 
`lsc` layers comments onto `eza`'s output (so colors, icons, and `--classify`
indicators survive), and it prefers an in-file `comment:` line over any sidecar
store — that comment travels with the file's bytes through iCloud, `rsync`,
and atomic editor saves.

## Where comments come from

For each file, `lsc` looks for a comment in two places, in order of precedence:

1. An in-file magic line near the top of a text file, matching `comment:`
   after a comment marker. Markers recognized are `//`, `#`, `--`, `;`. The match
   is case-insensitive and allows leading indentation.

   The first example below becomes the actual `lsc` comment for this `README.md`:

       // comment: docs for lsc (eza-with-comments)
       #  comment: alternative
       -- comment: or this

   Only the first 50 lines are scanned, and binary/non-UTF-8 files are
   skipped, so this is cheap and safe.

2. A per-directory manifest, `.lsc-comments.json`, mapping bare filename to
   comment. This is plain JSON content, so it syncs through iCloud and travels
   with the directory.

The magic line wins when both exist.

## Why not use xattrs?

iCloud sync strips non-Apple xattrs, so on macOS, comments vanished on
other machines. The manifest we use is ordinary file content, so it survives iCloud
sync, file eviction, editor atomic-saves, and `rsync` to other machines. The
in-file magic line is even more durable (it is part of the file's bytes), so
it is preferred for text files; the manifest covers everything else, including
binaries where a magic line can't live.

## Managing comments

See [Usage](#usage) below for the full command and flag reference (generated
from `lsc --help`).

`--set` refuses if FILE does not exist. `--set` and `--rm` still act, 
but warn on stderr, when an in-file magic
line shadows the manifest — because the magic line is what the listing will still
show after the operation. If the directory is read-only, `--set`/`--rm` print an error
and exit non-zero.

### Directory comments

A manifest entry keyed `.` is a directory's comment. Set it with
`setcomm . "these are my tools"` (i.e. `lsc --set . "..."`), and it prints as a
header line above the listing. It lives in the manifest only (a directory has no head to
scan for a magic line), keyed `.` in that directory's `.lsc-comments.json`, so
it travels with the folder like any other comment. (It also shows up in the parent
directory's listing.)

Because adding a comment to a directory writes to the manifest file inside it, you can
only add a comment to a directory you can write to (whereas you can use `lsc --set` to
add a comment to a non-writable file, provided you can write to its directory).

## Terminal-width behavior

The listing adapts to the current terminal width:

- The name column may grow up to `NAME_FRAC` of the terminal (clamped to
  `[NAME_MIN, NAME_MAX]`), so wide terminals show longer names before
  truncating and narrow ones cut sooner.
- The comment column starts just past the longest shown name.
- Comment text is clipped with an ellipsis so the whole line fits the terminal
  and never wraps to the next row.
- When `lsc` output is piped or redirected (not to a terminal), width detection
  falls back to `FALLBACK_WIDTH`.

Other display details: comment text is shown dim + italic (via
`COMMENT_STYLE`), and truncated names get a trailing ellipsis. If no file has
a comment, the listing is passed through unchanged.

## Recently-changed highlighting

A comment that changed within the last `HILITE_SECS` seconds (60 by default) is
drawn in a distinct highlight style (`HILITE_STYLE`, a muted gold) instead of
the usual dim italic, so a comment you just set stands out. This is on by
default; `--no-hilite-recent` turns it off for a run and `--hilite-recent`
forces it back on (`LSC_HILITE_RECENT=0` flips the default). 
Because the highlight only ever
recolors a row that already has a comment, a no-comment listing stays
byte-identical to plain eza whether the highlight is on or off.

"Recently changed" is judged per comment source: a manifest comment carries a
set-time, written by `--set` (so manifest entries become
`{"text": ..., "ts": "2026-06-23T14:05:00-07:00"}` — a human-readable local
timestamp).
A magic `comment:` line has no stored time, so its freshness is taken from the
file's modification time — editing a file is the only way to change its magic
comment anyway. (A hopefully-nice side effect is that recently changed files
with magic comments are briefly highlighted by `lsc`.)

## Install

On macOS, via Homebrew (pulls in eza automatically):

    brew install crufi/tap/lsc

From source, on any Unix:

    make install            # lsc -> ~/.local/bin, lsc.sh -> ~/.local/share/lsc
    make install PREFIX=/usr/local
    make install BINDIR=~/bin

`make install` copies the `lsc` command to a bin directory (which should be on your `PATH`) and
the `lsc.sh` shell functions to a data directory; it prints the exact `source`
line to add to your shell rc (`~/.bashrc` or `~/.zshrc`), and warns if the bin
directory is not on your `PATH`. `make uninstall` removes both. 

There are no pip
packages to install; lsc is a single Python 3.8+ script. See the shell-functions
section below.

## Nerd Font (needed for icons)

eza emits Private Use Area codepoints for icons; without a Nerd Font selected
in the terminal you get tofu boxes instead. Install one and pick the Mono variant
(single-cell glyphs, which the alignment math assumes), e.g. on macOS:

    brew install --cask font-jetbrains-mono-nerd-font

Then set the terminal font to "JetBrainsMono Nerd Font Mono". Test:

    eza --icons=always

`lsc` passes `--icons=always` to `eza` by default. If you don't want icons, change
the default behavior with

    export LSC_EZA_OPTS="--icons=never"

## Shell functions

The functions work in bash or zsh. `make install` puts `lsc.sh` at
`$PREFIX/share/lsc/lsc.sh` (so by default `~/.local/share/lsc/lsc.sh`) and
prints the line to add to your shell rc (`~/.bashrc` or `~/.zshrc`):

    source ~/.local/share/lsc/lsc.sh

It loads on the next shell. (If you would rather not install it, you can source
the copy in the repo instead — it is the same file.) The file sets `_eza_ignore`
to the manifest's filename, merging with any value you already have, so an
eza-based `ls` can hide the manifest; and it defines the `setcomm`/`rmcomm`/`getcomm` wrappers around `lsc --set|--rm|--get`. The `lsc` command itself comes from
`make install` and needs no function; to use the comment column for every
listing, `alias ls=lsc`.

## Usage

    setcomm runcpp.sh "compile+run wrapper with magic-comment flags"
    setcomm archive.zip "Q2 board deck, do not delete"
    lsc                 # current directory
    lsc ~/bin           # another directory, from anywhere

Full command and flag reference (generated from `lsc --help`; run `make readme`
to refresh):

<!-- begin help -->
```
Annotate files and directories with short comments that appear in a column
next to the names in an `eza` listing. With no action flag, lsc lists PATH (or
the current directory). Only a single directory argument is resolved for
comments; with multiple paths or globs, comments resolve against the current
directory. Any flag not listed below is passed through to eza, e.g.
`lsc -la --color=never`.

Usage:
  lsc [OPTION]... [PATH]...
  lsc --set FILE TEXT
  lsc --rm FILE
  lsc --get FILE

Options:
  --set FILE TEXT           set FILE's manifest comment (empty TEXT removes it,
                            same as --rm); `--set . TEXT` captions the directory

  --rm FILE                 remove FILE's manifest comment, if any

  --get FILE                print FILE's effective comment (inline or manifest)

  --fetch-icloud, --fetch   read evicted iCloud files too (forces an iCloud
                            download if needed; default skips them)

  --no-hilite-recent, --no-hilite   do not highlight just-changed comments (on by default)

  --hilite-recent, --hilite         force highlighting of just-changed comments on

  --version                 show version number and exit

  --help                    show this help and exit

Comments:
  Comments come from two sources, with an inline magic line taking precedence
  over the manifest. The inline form is a `comment:` line near the top of a text
  file, after a //, #, --, or ; marker (case-insensitive, optional indent). The
  manifest form is a per-directory .lsc-comments.json file mapping each bare
  filename to its comment text; it is plain JSON, so it syncs through iCloud and
  travels with the directory (unlike xattrs, which iCloud sync may strip).

  Both --set and --rm act on the manifest only; they warn (on stderr) but still
  act when an in-file magic line would shadow the manifest entry in a listing.

  A manifest entry keyed "." is the directory's own caption (set with
  `lsc --set . "..."`); it prints left-aligned as a header line above the
  listing.
```
<!-- end help -->

Directory argument support: `lsc DIR` resolves names against DIR, so comment
lookups work even when run from a different working directory. This covers the
single-directory case only. Multiple paths, file arguments, or globs fall back
to current-directory name resolution, because eza's --oneline output does not
record which directory each line came from.

## Tunables (top of lsc.py)

    MANIFEST_NAME  = ".lsc-comments.json"       # per-directory comment store
    NAME_FRAC      = 0.5        # max share of terminal width for the name column
    NAME_MIN       = 20         # never truncate names shorter than this
    NAME_MAX       = 60         # never let the name column grow past this
    GAP            = 2          # gap between names and the comment column
    FALLBACK_WIDTH = 80         # width used when output is piped (no tty)
    COMMENT_STYLE  = "2;3"      # ANSI SGR for comments: 2=dim, 3=italic; "" = plain
    HILITE_STYLE   = "38;5;179" # ANSI SGR for a recently-changed comment (gold)
    HILITE_SECS    = 60         # a comment changed within this many seconds is recent
    HILITE_RECENT  = True       # whether the recency highlight is on by default
    DATALESS_PLACEHOLDER =  "(not downloaded)"  # shown for evicted iCloud files

To pin the column instead of letting it shift as you resize, set `NAME_MIN`
and `NAME_MAX` close together (e.g. both near 38).

Several of these also take an environment-variable override, so you can tune
them without editing the file: `LSC_COMMENT_STYLE` and `LSC_HILITE_STYLE` set
the two comment styles (ANSI SGR strings), `LSC_HILITE_SECS` sets the recency
window, and `LSC_HILITE_RECENT=0` turns the highlight off by default (a
per-run `--no-hilite-recent` / `--hilite-recent` flag overrides it either way).

## Customizing the eza options

lsc passes a small set of eza flags by default (`--color=always`,
`--icons=always`, `--no-quotes`, `--classify`, `--group-directories-first`).
Set `LSC_EZA_OPTS` to change them, writing flags as if you were passing them
straight to eza:

    export LSC_EZA_OPTS="--icons=never --sort=size --git"

A flag that touches an option already in the defaults replaces that default in
place (so eza never sees a conflicting pair) — aliases included, so
`--colour=never` or `-F=never` are recognized as `--color` and `--classify`.
Any other flag is appended. Only `--oneline` is fixed: lsc's parser needs one
entry per line, so it is always sent and cannot be overridden. Note that
dropping `--no-quotes` makes comments disappear on filenames containing spaces
(eza quotes those names, and the lookup opens the name verbatim).

## Notes and caveats

- iCloud-evicted files are not read by default. Reading a file's head to find
  its magic `comment:` line would force macOS to download an evicted ("Optimize
  Mac Storage") file, so the listing skips that probe for dataless files and
  shows their manifest comment if one exists, otherwise a `(not downloaded)`
  placeholder, right-aligned to the terminal edge to read as a status note
  rather than a description (`DATALESS_PLACEHOLDER`; set to `""` to disable). Pass
  `--fetch-icloud` / `--fetch` (or set `LSC_FETCH_ICLOUD=1`) to read them anyway,
  accepting the downloads (and a delay). This is a no-op outside macOS, where the dataless flag
  does not exist.
- The manifest is keyed by bare filename and lives in the directory, so it
  travels when you move the folder. Renaming a file leaves its entry stale
  (harmless — it just stops matching). There is no `mv` subcommand (yet?) to
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

- A `mv` subcommand to move a manifest entry when a file is renamed. (But in practice, I 
  prefer inline text comments anyway.)
- Multi-directory arguments (`lsc dir1 dir2`) would need parsing eza's section
  headers to know which directory each name belongs to.
- Surviving into `eza -l` long-format output would need rework, since long
  format puts the name at the end of a metadata row.
