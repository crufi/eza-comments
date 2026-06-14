#!/usr/bin/env python3
"""
lsc - eza listing with an aligned comment column.

Runs eza once, then annotates each line with a short comment, aligned into a
column. ANSI colors and Nerd Font icons from eza are preserved; truncation is
ANSI-aware so escape sequences are never sliced mid-code.

Comments come from two places, in order of precedence:
  1. an in-file magic line near the top of a text file:
       //  #comment: <text>   (case-insensitive, optional indent)
  2. a per-directory manifest, MANIFEST_NAME, mapping filename -> comment.
     This is plain JSON content, so it syncs through iCloud and travels with
     the directory (unlike xattrs, which iCloud strips).

Subcommands manage the manifest:
  lsc                 list the current directory with comments
  lsc DIR             list DIR (comments resolved against DIR)
  lsc set FILE TEXT   set FILE's manifest comment (refuses if FILE is absent)
  lsc rm  FILE        remove FILE's manifest comment
  lsc get FILE        print FILE's effective comment

set and rm warn (on stderr) but still act when an in-file magic line shadows
the manifest, since the magic line is what the listing will actually show.
"""

# comment: python script driving my ls-with-comments

import os
import re
import sys
import json
import shutil
import subprocess
from itertools import islice

# ----- tunables ---------------------------------------------------------------

MANIFEST_NAME = ".lsc-comments.json"  # per-directory comment store
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
# themes), "3" = italic. Set to "" for plain text. Reset is appended
# automatically.
COMMENT_STYLE = "2;3"

# eza options to mirror the interactive `ls` shell function. --icons=always
# and --color=always are forced because output is piped here but we still want
# them rendered; 'oneline' gives one bare entry per line.
EZA_BASE = ["--oneline", "--color=always", "--icons=always", "--classify", "--no-quotes", "--group-directories-first"]

# classify indicator chars eza may append to a name (--classify)
CLASSIFY_CHARS = "*/=>@|"

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

# ----- width handling ---------------------------------------------------------

try:
    from wcwidth import wcswidth as _wcswidth

    def vis_width(s: str) -> int:
        w = _wcswidth(s)
        return w if w >= 0 else len(s)
except ImportError:
    # Fallback: count codepoints, but give Nerd Font PUA glyphs (U+E000-U+F8FF)
    # a width of 1. Good enough without the wcwidth dependency.
    def vis_width(s: str) -> int:
        return len(s)


def strip_ansi(s: str) -> str:
    return ANSI_RE.sub("", s)


def _is_pua(ch: str) -> bool:
    """True if ch is in any Private Use Area used by Nerd Fonts:
    BMP (U+E000-U+F8FF) or the Supplementary areas (U+F0000-U+FFFFD,
    U+100000-U+10FFFD). Nerd Font glyphs are spread across all three."""
    o = ord(ch)
    return (
        0xE000 <= o <= 0xF8FF
        or 0xF0000 <= o <= 0xFFFFD
        or 0x100000 <= o <= 0x10FFFD
    )


def visible_name(line: str) -> str:
    """Visible filename: ANSI stripped, leading icon+space removed if present,
    trailing classify indicator removed."""
    plain = strip_ansi(line)
    # eza with --icons prints: "<glyph> name". The glyph is a single PUA char
    # followed by a space. Strip a leading non-space run + one space.
    if " " in plain:
        head, _, rest = plain.partition(" ")
        # only treat as an icon if head is a single PUA glyph
        if len(head) == 1 and _is_pua(head):
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
    n = len(line)
    saw_ansi = False
    while i < n:
        m = ANSI_RE.match(line, i)
        if m:
            out.append(m.group())
            saw_ansi = True
            i = m.end()
            continue
        ch = line[i]
        cw = vis_width(ch)
        if width + cw > limit:
            break
        out.append(ch)
        width += cw
        i += 1
    if saw_ansi:
        out.append("\x1b[0m")  # ensure we don't bleed color past the cut
    return "".join(out)


# ----- manifest ---------------------------------------------------------------
#
# Comments are stored per-directory in a hidden JSON file (MANIFEST_NAME),
# mapping bare filename -> comment string. This is plain file content, so it
# syncs through iCloud and travels with the directory (unlike xattrs, which
# iCloud strips). A magic "comment:" line inside a text file still takes
# precedence over the manifest; see read_comment.

def _manifest_path(directory: str) -> str:
    return os.path.join(directory or ".", MANIFEST_NAME)


def load_manifest(directory: str) -> dict:
    """Return the directory's comment manifest as a dict, or {} if absent or
    unreadable."""
    try:
        with open(_manifest_path(directory), encoding="utf-8") as f:
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
    path = _manifest_path(directory)
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


def manifest_comment(path: str) -> str:
    """Manifest comment for a single file path, or ""."""
    directory, name = os.path.split(path)
    return load_manifest(directory).get(name, "")


# magic-comment line scanned as a fallback when no xattr is present:
#   //  #  ;   comment: <text>     (case-insensitive, optional indent)
_MAGIC_COMMENT_RE = re.compile(r"(?i)^\s*(?://|#|--|;)\s*comment:\s*(.*)$")


def search_head(path: str, pattern, max_lines: int = 50):
    """First regex match within the first max_lines lines, or None.
    Binary / undecodable / unreadable files return None."""
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


def magic_comment(path: str) -> str:
    """The in-file "comment:" magic line text, or "". Text files only."""
    if m := search_head(path, _MAGIC_COMMENT_RE):
        return m.group(1).strip()
    return ""


def read_comment(path: str) -> str:
    """Effective comment shown in the listing: an in-file magic "comment:" line
    wins, then the per-directory manifest."""
    return magic_comment(path) or manifest_comment(path)


# ----- main -------------------------------------------------------------------

def run_eza(args):
    ignore = os.environ.get("_eza_ignore", "")
    eza_bin = os.environ.get("EZA_BIN", "eza")
    cmd = [eza_bin, *EZA_BASE]
    if ignore:
        cmd.append(f"--ignore-glob={ignore}")
    cmd.extend(args)
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        sys.stderr.write(res.stderr)
        sys.exit(res.returncode)
    return [ln for ln in res.stdout.splitlines()]


def _base_dir(args):
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


def _style_comment(text: str) -> str:
    if not COMMENT_STYLE:
        return text
    return f"\x1b[{COMMENT_STYLE}m{text}\x1b[0m"


def clip_text(text: str, limit: int) -> str:
    """Clip plain text to `limit` visible columns, appending an ellipsis if it
    had to be cut. Returns "" if limit is too small to show anything useful."""
    if limit <= 0:
        return ""
    if vis_width(text) <= limit:
        return text
    if limit == 1:
        return "\u2026"
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
    return "".join(out) + "\u2026"


# ----- subcommands ------------------------------------------------------------

def _warn_if_shadowed(path: str, action: str) -> None:
    """If an in-file magic 'comment:' line exists, it takes precedence over the
    manifest in the listing. Warn (to stderr) but let the caller proceed."""
    magic = magic_comment(path)
    if magic:
        sys.stderr.write(
            f'lsc: note: in-file "comment:" line shadows the manifest for '
            f'{os.path.basename(path)}; the listing will {action} show: '
            f'"{magic}"\n'
        )


def cmd_set(argv) -> int:
    if len(argv) != 2:
        sys.stderr.write('usage: lsc set FILE "comment"\n')
        return 2
    path, comment = argv
    if not os.path.exists(path):
        sys.stderr.write(f"lsc: {path}: no such file (refusing to set)\n")
        return 1
    directory, name = os.path.split(path)
    data = load_manifest(directory)
    data[name] = comment
    if not save_manifest(directory, data):
        sys.stderr.write(
            f"lsc: cannot write manifest in {directory or '.'} "
            f"(read-only or permission denied)\n"
        )
        return 1
    _warn_if_shadowed(path, "still")
    return 0


def cmd_rm(argv) -> int:
    if len(argv) != 1:
        sys.stderr.write("usage: lsc rm FILE\n")
        return 2
    path = argv[0]
    directory, name = os.path.split(path)
    data = load_manifest(directory)
    if name in data:
        del data[name]
        if not save_manifest(directory, data):
            sys.stderr.write(
                f"lsc: cannot write manifest in {directory or '.'} "
                f"(read-only or permission denied)\n"
            )
            return 1
    else:
        sys.stderr.write(f"lsc: {name}: no manifest comment to remove\n")
    # even after removal, a magic line may keep showing a comment
    _warn_if_shadowed(path, "still")
    return 0


def cmd_get(argv) -> int:
    if len(argv) != 1:
        sys.stderr.write("usage: lsc get FILE\n")
        return 2
    print(read_comment(argv[0]))
    return 0


def main(argv):
    args = argv[1:]

    # subcommand dispatch: only the exact words set/rm/get are commands;
    # anything else (paths, flags) goes to the lister.
    if args and args[0] in ("set", "rm", "get"):
        return {"set": cmd_set, "rm": cmd_rm, "get": cmd_get}[args[0]](args[1:])

    lines = run_eza(args)

    base = _base_dir(args)

    names = [visible_name(ln) for ln in lines]
    # Resolve each name against the listed directory so comment lookups work
    # when lsc is given a directory argument from a different cwd.
    paths = [os.path.join(base, n) if base else n for n in names]
    # Full visible width of each line (icon + name + classify char), since that
    # is what actually occupies terminal columns. Aligning on this keeps the
    # truncated and non-truncated branches on the same origin.
    full_vis = [vis_width(strip_ansi(ln)) for ln in lines]
    comments = [read_comment(p) for p in paths]

    any_comments = any(comments)

    # Terminal width. shutil falls back to FALLBACK_WIDTH when stdout is not a
    # tty (e.g. lsc piped to a file), which is the right behavior — no point
    # truncating to a window that isn't there.
    width = shutil.get_terminal_size((FALLBACK_WIDTH, 24)).columns

    # Adaptive name-truncation point: up to NAME_FRAC of the terminal, clamped
    # to [NAME_MIN, NAME_MAX]. Wide terminals show longer names before cutting.
    # Also bounded by the terminal width itself (minus room for icon+ellipsis)
    # so an absurdly narrow window can't push a "truncated" name past the edge.
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

    out = []
    for line, fw, comment in zip(lines, full_vis, comments):
        shown = clip_text(comment, comment_budget) if comment else ""
        if any_truncate and fw > name_trunc:
            # always truncate when truncation is in play, even with no comment
            cut = truncate_ansi(line, name_trunc)
            tail = _style_comment(shown) if shown else ""
            out.append(f"{cut}\u2026 {tail}".rstrip())
        elif shown:
            pad = col - fw
            out.append(f"{line}{' ' * pad}{_style_comment(shown)}")
        else:
            out.append(line)

    sys.stdout.write("\n".join(out) + ("\n" if out else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))