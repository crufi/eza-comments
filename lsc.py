#!/usr/bin/env python3
"""
lsc - eza listing with an aligned comment column.

Allows annotating files (and directories) with short comments that show up
in a column next to file names in an `eza` listing. ANSI colors and Nerd Font
icons from eza are preserved; truncation is ANSI-aware so escape sequences
are never sliced mid-code.

Comments can come from two places, in order of precedence:

  1. an inline magic line near the top of a text file:
       //  #comment: <text>   (case-insensitive, optional indent)

  2. a per-directory manifest, MANIFEST_NAME, mapping filename -> comment.
     This is plain JSON content, so it can sync through iCloud and travels with
     the directory (unlike, e.g., xattrs, which iCloud sync may strip).

Manage the manifest with action flags (any other args specify the path to list):

  lsc                           list the current directory with comments
  lsc DIR                       list specified directory (one dir only; with
                                multiple paths or globs, comments resolve
                                against the current directory)
  lsc --fetch-icloud, --fetch   read evicted iCloud files too (forces iCloud
                                download if needed; default skips this)
  lsc --set FILE TEXT           set FILE's manifest comment (empty TEXT removes
                                it, same as --rm)
  lsc --rm  FILE                remove FILE's manifest comment, if any
  lsc --get FILE                print FILE's effective comment (inline or manifest)
  lsc --help                    show this help
  lsc --version                 show version number

--set and --rm warn (on stderr) but still act when an in-file magic line shadows
the manifest, since the magic line is still what a listing will actually show.

A manifest entry keyed "." (set with `lsc --set . "..."`) is the directory's own
caption: it prints left-aligned, in the comment style, as a header line above
the listing.
"""

# comment: main python script for lsc (eza-with-comments)

import os
import re
import sys
import json
import shutil
import subprocess
import shlex
from datetime import datetime
from itertools import islice

__version__ = "0.1.0"

# ----- tunables ---------------------------------------------------------------

MANIFEST_NAME = ".lsc-comments.json"  # per-directory comment store
DIR_KEY = "."  # manifest key for the directory's own caption (header line)
# Layout is adaptive to terminal width W. The name column may grow up to
# NAME_FRAC * W (so wide terminals show longer names before truncating), but
# never below NAME_MIN or above NAME_MAX. The comment column starts just past
# the longest shown name, and comment text is clipped so no line exceeds W.
NAME_FRAC = 0.5        # max share of terminal width the name column may take
NAME_MIN = 20          # never truncate names shorter than this
NAME_MAX = 60          # never let the name column grow past this
GAP = 2                # spaces between names and the comment column
FALLBACK_WIDTH = 80    # used when terminal width can't be detected (piped)

# ANSI styling applied to the comment text. "2" = dim (renders gray in most
# themes), "3" = italic. Set to "" for plain text. LSC_COMMENT_STYLE overrides it.
COMMENT_STYLE = os.environ.get("LSC_COMMENT_STYLE") or "2;3"

# Recently-changed comments are highlighted so a just-set comment stands out. A
# comment counts as recent when it was changed within HILITE_SECS: for a manifest
# comment that is the entry's stored "ts"; for a magic comment it is the file's
# mtime (editing the file is the only way to change its magic line). On by
# default; --no-hilite-recent (or LSC_HILITE_RECENT=0) turns it off. The
# highlight only ever repaints rows that already have a comment, so a no-comment
# listing stays byte-identical to plain eza whether it is on or off.
HILITE_STYLE = os.environ.get("LSC_HILITE_STYLE") or "38;5;179"  # a muted gold
HILITE_SECS = 60       # a comment changed within this many seconds is "recent"
if os.environ.get("LSC_HILITE_SECS", "").isdigit():
    HILITE_SECS = int(os.environ["LSC_HILITE_SECS"])
HILITE_RECENT = os.environ.get("LSC_HILITE_RECENT", "1").lower() not in (
    "0", "false", "no", "off", "")

# Shown in the comment column for an evicted (dataless) iCloud file that has no
# manifest comment, so the line reads as deliberately not-yet-downloaded rather
# than blank. It appears only while the listing is skipping evicted files (i.e.
# without --fetch-icloud). Set to "" to leave such files blank instead.
UNFETCHED_ICLOUD_PLACEHOLDER = "(not downloaded)"

# eza flags lsc always passes. --oneline is the only structural requirement
# (the parser needs one bare entry per line) and cannot be overridden.
EZA_REQUIRED = ["--oneline"]

# Default eza flags, each overridable via LSC_EZA_OPTS. '--color=always' and
# '--icons=always' are forced on because output is piped here (eza would otherwise
# drop them); '--no-quotes' keeps spaced filenames bare so comment lookups work
# cleanly (see get_effective_comment / CLAUDE.md); the rest are implementer's preference.
EZA_DEFAULTS = ["--color=always", "--icons=always", "--no-quotes",
                "--classify", "--group-directories-first"]

# Match flag variants to a single key per flag to allow overriding defaults:
#
# LSC_EZA_OPTS lets the user pass flags as if straight to eza. A user flag whose
# option is already in EZA_DEFAULTS replaces that default in place (so eza never
# sees a duplicate/conflicting pair); anything else is appended. Matching is by
# option identity, so every spelling eza accepts for a defaulted option maps to
# one key here -- only the few options EZA_DEFAULTS sets need an entry.
EZA_OPT_KEY = {
    "--color": "color",
    "--colour": "color",

    "--icons": "icons",

    "--quotes": "quotes",
    "--no-quotes": "quotes",

    "--classify": "classify",
    "-F": "classify",

    "--group-directories-first": "group",
}

# classification indicator chars eza may append to a name (--classify)
CLASSIFY_CHARS = "*/=>@|"

ANSI_STYLING_RE = re.compile(r"\x1b\[[0-9;]*m")

# ----- width handling ---------------------------------------------------------

try:
    from wcwidth import wcswidth as _wcswidth

    def vis_width(s: str) -> int:
        w = _wcswidth(s)
        return w if w >= 0 else len(s)
except ImportError:
    # Fallback: count codepoints, good enough without the wcwidth dependency.
    def vis_width(s: str) -> int:
        return len(s)


def strip_ansi_styling(s: str) -> str:
    return ANSI_STYLING_RE.sub("", s)


def is_pua(ch: str) -> bool:
    """True if ch is in any Private Use Area used by Nerd Fonts:
    BMP (U+E000-U+F8FF) or the Supplementary areas (U+F0000-U+FFFFD,
    U+100000-U+10FFFD)."""
    o = ord(ch)
    return (
        0xE000 <= o <= 0xF8FF
        or 0xF0000 <= o <= 0xFFFFD
        or 0x100000 <= o <= 0x10FFFD
    )


def get_clean_filename(line: str) -> str:
    """Visible filename: ANSI stripped, leading icon+space removed if present,
    trailing classify indicator removed."""
    plain = strip_ansi_styling(line)
    # eza with --icons prints: "<glyph> name". The glyph is a single PUA char
    # followed by a space. Strip a leading non-space run + one space.
    if " " in plain:
        head, _, rest = plain.partition(" ")
        # only treat as an icon if head is a single PUA glyph
        if len(head) == 1 and is_pua(head):
            plain = rest
    if plain and plain[-1] in CLASSIFY_CHARS:
        plain = plain[:-1]
    return plain


def truncate_ansi(line: str, limit: int) -> str:
    """Return `line` truncated to `limit` visible columns, preserving ANSI
    escape sequences (they are copied through without counting toward width).
    Leaves color state as-is; a reset is appended to be safe."""
    out = []
    width = 0
    i = 0
    saw_ansi_styling = False
    while i < len(line):
        m = ANSI_STYLING_RE.match(line, i)
        if m:
            out.append(m.group())
            saw_ansi_styling = True
            i = m.end()
            continue
        ch = line[i]
        cw = vis_width(ch)
        if width + cw > limit:
            break
        out.append(ch)
        width += cw
        i += 1
    if saw_ansi_styling:
        out.append("\x1b[0m")  # reset any applied ANSI styling
    return "".join(out)


# ----- manifest ---------------------------------------------------------------
#
# Comments are stored per-directory in a hidden JSON file (MANIFEST_NAME),
# mapping bare filename -> comment string. This is plain file content, so it
# syncs through iCloud and travels with the directory (unlike xattrs, which
# iCloud strips). A magic "comment:" line inside a text file still takes
# precedence over the manifest; see get_effective_comment.

def get_manifest_path(directory: str) -> str:
    return os.path.join(directory or ".", MANIFEST_NAME)


def load_manifest(directory: str) -> dict:
    """Return the directory's comment manifest as a dict, or {} if absent or
    unreadable."""
    try:
        with open(get_manifest_path(directory), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_manifest(directory: str, data: dict) -> bool:
    """Write the manifest atomically (temp file + rename) so a crash mid-write
    can't corrupt it. An empty manifest removes the file. Returns True on
    success, False if the directory isn't writable or the write fails (the
    caller reports it); never raises for an ordinary permission or I/O problem,
    and never leaves an orphaned temp file behind."""
    path = get_manifest_path(directory)
    if not data:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        except OSError:
            return False
        return True
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)        # clean up a partial temp file
        except OSError:
            pass
        return False
    return True


def entry_text(value) -> str:
    """Comment text from a manifest value. A value is either a bare string
    (legacy, or any entry with no recorded time) or an object
    {"text": ..., "ts": ...}. Both forms are read; cmd_set_rm writes only the
    object form, so old manifests keep working unchanged."""
    if isinstance(value, dict):
        return value.get("text", "") or ""
    return value or ""


def entry_ts(value):
    """ISO-8601 set-time stored on a manifest value, or None. Bare-string and
    timeless entries have none, so they are never highlighted as recent."""
    return value.get("ts") if isinstance(value, dict) else None


def get_manifest_value(path: str):
    """Raw manifest value (string or object) for a path, or "" if none."""
    directory, name = os.path.split(path)
    return load_manifest(directory).get(name, "")


def get_manifest_comment(path: str) -> str:
    """Manifest comment for a single file path, or empty string."""
    return entry_text(get_manifest_value(path))


# regex for magic-comment line:
#   //  #  ;  --  comment: <text>     (case-insensitive, optional indent)
MAGIC_COMMENT_RE = re.compile(r"(?i)^\s*(?://|#|--|;)\s*comment:\s*(.*)$")

def search_head(path: str, pattern, max_lines: int = 50):
    """First regex match within the first max_lines lines, or None.
    Binary/undecodable/unreadable files return None."""
    rx = re.compile(pattern) if isinstance(pattern, str) else pattern
    try:
        with open(path, "rb") as fb:
            if b"\x00" in fb.read(8192):
                return None  # looks binary
        with open(path, encoding="utf-8") as f:
            for line in islice(f, max_lines):
                m = rx.search(line)
                if m:
                    return m
    except (UnicodeDecodeError, OSError):
        return None
    return None


# macOS marks an evicted ("Optimize Mac Storage") iCloud file as dataless: its
# contents are not on disk, and the first read of one forces a download. The
# listing skips the magic-comment probe for such files so it never silently
# pulls data down; pass fetch_icloud=True (the lister's --fetch-icloud flag)
# to read them anyway. st_flags is macOS-only, so this is a no-op elsewhere
# (e.g. Linux), where is_dataless always returns False and nothing is skipped.
SF_DATALESS = 0x40000000


def is_dataless(path: str) -> bool:
    """True if path is an evicted iCloud file whose bytes are not local. Uses
    the macOS-only SF_DATALESS st_flags bit; returns False where st_flags is
    unavailable. stat() alone does not trigger a download."""
    try:
        flags = getattr(os.stat(path), "st_flags", 0)
    except OSError:
        return False
    return bool(flags & SF_DATALESS)


def get_magic_comment(path: str) -> str:
    """The in-file "comment:" magic line text, or "". Text files only."""
    if m := search_head(path, MAGIC_COMMENT_RE):
        return m.group(1).strip()
    return ""


def get_dir_caption_value(path: str, fetch_icloud: bool = True):
    """Raw manifest value (string or object) for a directory's own "." caption,
    or "". This is the same caption shown as the header when that directory is
    listed directly; here it lets a subdirectory describe itself in its parent's
    listing. The read is skipped (returns "") for an evicted manifest when
    fetch_icloud is False, so a parent listing never forces an iCloud download
    just to read a subdir's caption."""
    if not fetch_icloud and is_dataless(get_manifest_path(path)):
        return ""
    return load_manifest(path).get(DIR_KEY, "")


def get_dir_caption(path: str, fetch_icloud: bool = True) -> str:
    """A directory's own "." caption text (see get_dir_caption_value)."""
    return entry_text(get_dir_caption_value(path, fetch_icloud))


def now_ts():
    """Current local time as a timezone-aware datetime. LSC_NOW (an ISO-8601
    string) overrides it so tests can pin "now" and keep recency deterministic."""
    override = os.environ.get("LSC_NOW")
    if override:
        try:
            return datetime.fromisoformat(override)
        except ValueError:
            pass
    return datetime.now().astimezone()


def ts_is_recent(ts, now=None) -> bool:
    """True if the ISO-8601 set-time `ts` is within HILITE_SECS of now. None or
    an unparseable/naive value -> False, so legacy timeless entries never
    highlight. A future ts (negative delta, e.g. clock skew) is not "recent"."""
    if not ts:
        return False
    now = now or now_ts()
    try:
        delta = (now - datetime.fromisoformat(ts)).total_seconds()
    except (ValueError, TypeError):
        return False
    return 0 <= delta <= HILITE_SECS


def mtime_is_recent(path: str, now=None) -> bool:
    """True if path's mtime is within HILITE_SECS of now. Used for a magic
    comment, whose only way to change is editing the file itself. stat does not
    trigger an iCloud download."""
    try:
        mtime = os.stat(path).st_mtime
    except OSError:
        return False
    now = now or now_ts()
    return 0 <= (now.timestamp() - mtime) <= HILITE_SECS


def resolve_comment(path: str, fetch_icloud: bool = True):
    """Return (comment, recent) for the listing: the effective comment string
    plus whether the shown comment was changed within HILITE_SECS. Text and
    freshness are decided on one precedence path so they cannot disagree.

    For a directory, its own "." caption (its stored ts) wins over a parent
    manifest's entry for it — the same "the comment that lives with the item
    wins" rule that makes a file's magic line beat the manifest; a directory has
    no head to scan, so no magic line is involved. For a file, a magic
    "comment:" line (recency = file mtime) wins, then the per-directory manifest
    (recency = stored ts). When fetch_icloud is False and the file is an evicted
    (dataless) iCloud file its contents are not read, so only the manifest
    applies; if it has no entry the UNFETCHED_ICLOUD_PLACEHOLDER is shown (never
    recent). Otherwise no comment returns ("", False)."""
    now = now_ts()
    if os.path.isdir(path):
        value = get_dir_caption_value(path, fetch_icloud)
        if entry_text(value):
            return entry_text(value), ts_is_recent(entry_ts(value), now)
        parent = get_manifest_value(path)
        return entry_text(parent), ts_is_recent(entry_ts(parent), now)
    if not fetch_icloud and is_dataless(path):
        value = get_manifest_value(path)
        text = entry_text(value)
        if text:
            return text, ts_is_recent(entry_ts(value), now)
        return UNFETCHED_ICLOUD_PLACEHOLDER, False
    if magic := get_magic_comment(path):
        return magic, mtime_is_recent(path, now)
    value = get_manifest_value(path)
    return entry_text(value), ts_is_recent(entry_ts(value), now)


def get_effective_comment(path: str, fetch_icloud: bool = True) -> str:
    """Effective comment text for the listing (see resolve_comment for the
    precedence rules and the recency flag the listing uses)."""
    return resolve_comment(path, fetch_icloud)[0]


# ----- options handling ---------------------------------------------------------------------------

def opt_key(flag):
    """Identity key for an eza flag, ignoring any =value; None if the flag is
    not one of the options lsc sets a default for."""
    return EZA_OPT_KEY.get(flag.split("=", 1)[0])


def eza_opts():
    """EZA_DEFAULTS with any LSC_EZA_OPTS overrides applied in place, plus the
    user's extra (non-defaulted) flags appended. Lets the user pass flags as if
    straight to eza while lsc avoids handing eza a duplicate of an option it
    already defaults."""
    override = {}   # option key -> the user's flag, replacing the default
    extra = []      # user flags that touch no default
    for flag in shlex.split(os.environ.get("LSC_EZA_OPTS", "")):
        key = opt_key(flag)
        if key is None:
            extra.append(flag)
        else:
            override[key] = flag
    merged = [override.get(opt_key(d), d) for d in EZA_DEFAULTS]
    return merged + extra


def run_eza(args):
    ignore = os.environ.get("_eza_ignore", "")
    eza_bin = os.environ.get("EZA_BIN", "eza")
    cmd = [eza_bin, *EZA_REQUIRED, *eza_opts()]
    if ignore:
        cmd.append(f"--ignore-glob={ignore}")
    cmd.extend(args)
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
    except OSError as e:
        sys.stderr.write(f"lsc: cannot run {eza_bin!r}: {e}\n")
        sys.exit(1)
    if res.returncode != 0:
        sys.stderr.write(res.stderr)
        sys.exit(res.returncode)
    return res.stdout.splitlines()


def base_dir(args):
    """If the args denote a single directory to list, return it so bare names
    from eza can be resolved against it. Otherwise return "" (names are taken
    relative to the current directory, the existing behavior).

    Only the simple, common case is handled: a lone directory path with no
    globs. Multiple paths, file arguments, or globs keep the bare-name
    behavior, since eza's --oneline output doesn't say which directory each
    line came from."""
    non_flags = [a for a in args if not a.startswith("-")]
    if len(non_flags) == 1 and os.path.isdir(non_flags[0]):
        return non_flags[0]
    return ""


def style_comment(text: str, recent: bool = False) -> str:
    style = HILITE_STYLE if recent else COMMENT_STYLE
    if not style:
        return text
    return f"\x1b[{style}m{text}\x1b[0m"


def clip_text(text: str, limit: int) -> str:
    """Clip plain text to `limit` visible columns, appending an ellipsis if it
    had to be cut. Returns "" if limit is too small to show anything useful."""
    if limit <= 0:
        return ""
    if vis_width(text) <= limit:
        return text
    ELLIPSIS = "\u2026"
    if limit == 1:
        return ELLIPSIS
    # reserve one column for the ellipsis
    budget = limit - 1
    out = []
    w = 0
    for ch in text:
        cw = vis_width(ch)
        if w + cw > budget:
            break
        out.append(ch)
        w += cw
    return "".join(out) + ELLIPSIS


# ----- flags --------------------------------------------------------------------------------------

def warn_if_shadowed(path: str) -> None:
    """A comment that lives with the item shadows the manifest entry just
    written, so the listing won't show the manifest one. For a file that's an
    in-file magic 'comment:' line; for a directory it's the directory's own '.'
    caption, which beats a parent manifest's entry for that directory. Warn (to
    stderr) but let the caller proceed. Captioning a directory itself
    ('--set DIR/.', name == DIR_KEY) is excluded — that entry is the caption,
    not something it shadows."""
    _, name = os.path.split(path)
    if os.path.isdir(path) and name != DIR_KEY:
        caption = get_dir_caption(path)
        if caption:
            sys.stderr.write(
                f'lsc: note: {name} has its own "." caption, which shadows the lsc '
                f'comment manifest entry; the listing will still show: "{caption}"\n'
            )
        return
    magic = get_magic_comment(path)
    if magic:
        sys.stderr.write(
            f'lsc: note: in-file "comment:" line shadows the lsc comment manifest for '
            f'{os.path.basename(path)}; the listing will still show: '
            f'"{magic}"\n'
        )


def cmd_set_rm(argv, remove: bool) -> int:
    """Set or remove a file's manifest comment. With remove=False, argv is
    FILE plus the comment text to store; '--set' refuses if the file is missing
    (catches typos / wrong cwd). An empty comment ('--set FILE ""') removes the
    entry, same as '--rm', since "" and a missing entry look identical in a
    listing. With remove=True, argv is just FILE and the entry is deleted if
    present. Either way a surviving in-file magic line is flagged afterward,
    since that is what a listing will actually show."""
    if remove:
        if len(argv) != 1:
            sys.stderr.write("usage: lsc --rm FILE\n")
            return 2
        path = argv[0]
        comment = None
    else:
        if len(argv) != 2:
            sys.stderr.write('usage: lsc --set FILE "comment"\n')
            return 2
        path, comment = argv
        # '--set' refuses on a missing file (typo / wrong cwd); '--rm' does not (so
        # an orphaned entry for a deleted/renamed file can still be cleared)
        if not os.path.exists(path):
            sys.stderr.write(f"lsc: {path}: target file does not exist (doing nothing)\n")
            return 1

    directory, name = os.path.split(path)
    data = load_manifest(directory)

    if remove and name not in data:
        # '--rm' warns if nothing to remove ('--set ""' does not):
        sys.stderr.write(f"lsc: {name}: no manifest comment to remove (doing nothing)\n")
        # we'll still warn_if_shadowed() below, since magic comment might persist
    else:
        if comment:
            # Store as an object carrying the local set-time (ISO-8601, seconds
            # resolution, no nanos) so the listing can highlight a just-changed
            # comment. entry_text/entry_ts still read the older bare-string form.
            data[name] = {"text": comment,
                          "ts": now_ts().isoformat(timespec="seconds")}
        elif name in data:
            del data[name]
        if not save_manifest(directory, data):
            sys.stderr.write(
                f"lsc: cannot write manifest in {directory or '.'} :"
                f"read-only or permission denied (doing nothing)\n"
            )
            return 1

    warn_if_shadowed(path)
    return 0


def cmd_get(argv) -> int:
    """Display a single file's comment string, or an empty string (i.e., newline) if none."""
    if len(argv) != 1:
        sys.stderr.write("usage: lsc --get FILE\n")
        return 2
    print(get_effective_comment(argv[0]))
    return 0


# ----- main entry point ---------------------------------------------------------------------------

def main(argv):
    # Error code contract (following Unix/Linux convention):
    #   0 = success
    #   1 = runtime failure (missing target, unwritable manifest, eza not runnable)
    #   2 = usage error (wrong arg count, conflicting action flags)
    # and when eza itself fails, its own returncode is propagated unchanged
    # (see run_eza).
    args = argv[1:]

    # '--help'/'--version' describe lsc itself and must not fall through to eza
    # (which has its own). Long forms only.
    if "--help" in args:
        sys.stdout.write((__doc__ or "").strip() + "\n")
        return 0
    if "--version" in args:
        print(f"lsc {__version__}")
        return 0

    # Management actions are flags, not subcommands, so a bare word is always a
    # path to list (a directory literally named "set" would otherwise collide).
    actions = {
        "--set": lambda a: cmd_set_rm(a, remove=False),
        "--get": cmd_get,
        "--rm": lambda a: cmd_set_rm(a, remove=True),
    }
    chosen = [a for a in args if a in actions]
    if chosen:
        if len(chosen) > 1:
            sys.stderr.write("lsc: choose only one of --set, --get, --rm\n")
            return 2
        flag = chosen[0]
        return actions[flag]([a for a in args if a != flag])

    # '--fetch-icloud' (or the shorthand '--fetch') forces reading evicted iCloud
    # files for their magic comment; the default skips them so a listing never
    # triggers a download. The LSC_FETCH_ICLOUD env var does the same. These
    # flags are consumed here so they are never handed to eza.
    fetch_flags = {"--fetch-icloud", "--fetch"}
    fetch_icloud = (
        any(a in fetch_flags for a in args)
        or bool(os.environ.get("LSC_FETCH_ICLOUD"))
    )
    args = [a for a in args if a not in fetch_flags]

    # Recently-changed comments are highlighted by default. The long-form flags
    # (no short form, matching the rest of lsc) force it on or off for this run,
    # overriding the LSC_HILITE_RECENT default; "-recent" is optional in each.
    # Consumed here so they are never handed to eza. Off wins if both are given.
    hilite = HILITE_RECENT
    if any(a in ("--hilite-recent", "--hilite") for a in args):
        hilite = True
    if any(a in ("--no-hilite-recent", "--no-hilite") for a in args):
        hilite = False
    args = [a for a in args
            if a not in ("--hilite-recent", "--hilite",
                         "--no-hilite-recent", "--no-hilite")]

    lines = run_eza(args)
    base = base_dir(args)

    names = [get_clean_filename(ln) for ln in lines]

    # Resolve each name against the listed directory so comment lookups work
    # when lsc is given a directory argument from a different cwd.
    paths = [os.path.join(base, n) if base else n for n in names]

    # Full visible width of each line (icon + name + classify char), since that
    # is what actually occupies terminal columns. Aligning on this keeps the
    # truncated and non-truncated branches on the same origin.
    full_vis = [vis_width(strip_ansi_styling(ln)) for ln in lines]
    resolved = [resolve_comment(p, fetch_icloud) for p in paths]
    comments = [text for text, _ in resolved]
    # A row's comment is highlighted only when highlighting is on and the comment
    # is recent; folding `hilite` in here keeps the render loop style-agnostic.
    recents = [hilite and recent for _, recent in resolved]

    # A manifest entry keyed "." is the directory's own caption. It is shown
    # left-aligned, in the comment style, as a header line above the listing.
    # Manifest only (directories can't have magic comments); must set with '--set'.
    dir_value = load_manifest(base).get(DIR_KEY, "")
    dir_comment = entry_text(dir_value)
    dir_recent = hilite and ts_is_recent(entry_ts(dir_value))

    any_comments = any(comments)

    # Terminal width (shutil falls back to FALLBACK_WIDTH when stdout is not a
    # tty (e.g. lsc piped to a file))
    width = shutil.get_terminal_size((FALLBACK_WIDTH, 24)).columns

    # Adaptive name-truncation point: up to NAME_FRAC of the terminal, clamped
    # to [NAME_MIN, NAME_MAX]. Wide terminals show longer names before cutting.
    # Also bounded by the terminal width itself (minus room for icon+ellipsis)
    # so a skinny window can't push a "truncated" name past the edge.
    name_trunc = max(NAME_MIN, min(NAME_MAX, int(width * NAME_FRAC)))
    name_trunc = min(name_trunc, max(1, width - 3))

    any_truncate = any_comments and any(fw > name_trunc for fw in full_vis)

    # Comment column origin:
    #  - if some name will be truncated, the column is fixed at name_trunc + 2
    #    (a truncated name occupies name_trunc + ellipsis + space), and every
    #    over-long name is capped so none can run into the column.
    #  - otherwise snug the column to the longest name (+ GAP).
    if any_truncate:
        col = name_trunc + 2
    else:
        col = max(full_vis, default=0) + GAP

    # Space available for comment text after the column, leaving the line at
    # most `width` columns so it never wraps into the next line.
    comment_budget = max(0, width - col)

    # Render the listing line by line:
    out = []

    if dir_comment:
        out.append(style_comment(clip_text(dir_comment, width), dir_recent))

    for line, fw, comment, recent in zip(lines, full_vis, comments, recents):
        shown = clip_text(comment, comment_budget) if comment else ""
        if any_truncate and fw > name_trunc:
            # always truncate when truncation is in play, even with no comment
            cut = truncate_ansi(line, name_trunc)
            tail = style_comment(shown, recent) if shown else ""
            out.append(f"{cut}\u2026 {tail}".rstrip())
        elif shown:
            # The unfetched iCloud placeholder is right-aligned to the terminal's right
            # edge (it's a status note, not a description); a real comment sits
            # left-aligned in the shared column. Fall back to the column if the
            # name leaves too little room to right-align cleanly.
            if comment == UNFETCHED_ICLOUD_PLACEHOLDER:
                rpad = width - fw - vis_width(comment)
                if rpad >= GAP:
                    out.append(f"{line}{' ' * rpad}{style_comment(comment)}")
                    continue
            pad = col - fw
            out.append(f"{line}{' ' * pad}{style_comment(shown, recent)}")
        else:
            out.append(line)

    sys.stdout.write("\n".join(out) + ("\n" if out else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
