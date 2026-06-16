---
# comment: project context for the lsc comment-column tool
---
# CLAUDE.md

Guidance for working on this project. Read before editing `lsc.py`.

## What this is

`lsc` runs `eza` once and annotates each line with a short per-file comment in
an aligned column, preserving eza's colors and Nerd Font icons. It is a single
Python file (`lsc.py`) plus thin zsh wrappers. There are no dependencies;
`wcwidth` is used if importable but not required.

`make install` puts the script on PATH as `lsc` (default `~/.local/bin/lsc`)
and copies `lsc.zsh` to `$PREFIX/share/lsc/` (default `~/.local/share/lsc/`);
locations are overridable via PREFIX/BINDIR/DATADIR, and a leading `~` in an
override is expanded in the recipe so it never lands on disk literally. Users
source the installed `lsc.zsh` from `~/.zshrc`:

    ls()      -> eza ... --ignore-glob="$_eza_ignore"  # plain listing, manifest hidden
    setcomm() -> lsc set "$@"    # write a manifest comment
    rmcomm()  -> lsc rm  "$@"    # remove a manifest comment
    getcomm() -> lsc get "$@"    # print effective comment

## Where comments come from (precedence matters)

1. An in-file magic line in the first 50 lines of a text file:
   `(?i)^\s*(?://|#|--|;)\s*comment:\s*(.*)$`. Binary / non-UTF-8 files are
   skipped (null-byte probe + decode guard).
2. A per-directory JSON manifest, `.lsc-comments.json`, mapping bare filename
   to comment string.

The magic line wins over the manifest. `set`/`rm` operate on the manifest only;
they warn (stderr) but still act when a magic line shadows the manifest.

The manifest key `.` (constant `DIR_KEY`) is special: it is the directory's own
caption, not a file. The lister reads `load_manifest(base).get(DIR_KEY)` and, if
present, emits it as the first output line — left-aligned at column zero, in the
comment style, above the listing. It is manifest-only (a directory has no head
to scan) and is set with `lsc set . "..."` (which `os.path.split` resolves to
`name == "."` in that directory's manifest, so no special-casing in `cmd_set`).

## Design decisions and their reasons (do not silently reverse these)

- **No xattrs.** An earlier version stored comments in a `user.comment`
  extended attribute. It was removed because iCloud sync strips non-Apple
  xattrs, so comments vanished on sibling Macs. Storage must be plain file
  content (manifest) or in-file (magic line) so it survives iCloud, file
  eviction, editor atomic-saves, and rsync. Do not reintroduce xattrs as the
  primary store.
- **Magic line beats manifest** because the in-file comment is the most
  durable (travels with the bytes) and is self-documenting.
- **Manifest is per-directory, keyed by bare filename**, not a central
  path-keyed file. This makes comments travel when a directory is moved, and
  avoids one global merge-conflict magnet across machines. Trade-off: renaming
  a file orphans its entry (harmless; just stops matching).
- **`set` refuses if the file does not exist** (catches typos / wrong cwd).
- **Layout is terminal-width adaptive.** Name column scales to the terminal,
  comments clip with an ellipsis so no line ever wraps. When stdout is not a
  tty (piped), width falls back to `FALLBACK_WIDTH` and output is byte-
  identical to plain eza when no comments exist.

## Gotchas that caused real bugs (regression-prone areas)

- **Nerd Font icons span three PUA ranges.** `visible_name` strips the leading
  icon glyph; `_is_pua` must cover BMP (U+E000–U+F8FF) AND both Supplementary
  areas (U+F0000–U+FFFFD, U+100000–U+10FFFD). A BMP-only check silently failed
  on real eza output (icons like U+F086F), producing mangled names and missing
  comments. Test with a Supplementary-PUA icon, not just U+E0A0.
- **eza filenames must be bare for lookups to work.** `read_comment` opens the
  name eza printed. If eza quotes spaced names (`'My File.txt'`) the open
  fails. `EZA_BASE` controls this; keep `--no-quotes` if spaced filenames need
  comments.
- **ANSI-aware truncation.** Never slice a colored line at a visible-column
  count without preserving escape sequences and appending a reset, or color
  bleeds / escapes get cut mid-sequence. See `truncate_ansi` and `clip_text`.
- **Width math is icon-inclusive.** Column positions are measured on the full
  visible line (icon + name + classify char), so truncation and padding share
  one origin. Mixing name-space and line-space measurements misaligns the
  column.
- **Write failures must not raise.** `save_manifest` returns a bool and cleans
  up its temp file on failure; `cmd_set`/`cmd_rm` report a clean error and exit
  non-zero. A read-only directory must not produce a traceback.
- **Reading a file triggers iCloud downloads.** The magic-comment probe opens
  every listed file's head; for an evicted ("Optimize Mac Storage") file that
  read forces macOS to materialize it from iCloud, which is slow and uses data.
  The listing therefore skips the probe for dataless files (`_is_dataless`, the
  `SF_DATALESS` st_flags bit) unless `--probe-evicted` / `--probe` /
  `LSC_PROBE_EVICTED` is
  set, falling back to the manifest (or `DATALESS_PLACEHOLDER` when the manifest
  has no entry). Do not move the probe ahead of this guard,
  and do not assume `stat` is enough — it is the open/read that downloads, not
  the stat. `st_flags` is macOS-only, so the guard no-ops elsewhere.

## Key functions

- `read_comment(path, probe_evicted=True)` — effective comment:
  `magic_comment(path, probe_evicted) or manifest_comment(path)`. The lister
  passes `probe_evicted=False` by default; `set`/`rm`/`get` keep the default.
- `magic_comment` / `manifest_comment` — the two sources.
- `_is_dataless` — macOS SF_DATALESS check; gates the magic-comment probe so a
  listing never forces an iCloud download.
- `search_head` — binary-guarded, islice-capped (50 lines) regex scan.
- `load_manifest` / `save_manifest` — JSON read / atomic write (temp+rename,
  auto-deletes when empty, returns False on failure).
- `visible_name` / `_is_pua` — recover the bare filename from an eza line.
- `truncate_ansi` / `clip_text` — width-bounded, ANSI-safe cutting.
- `_base_dir` — resolve `lsc DIR` names against DIR (single-dir case only).
- `cmd_set` / `cmd_rm` / `cmd_get` — manifest CRUD; dispatched in `main` on
  argv[1] in {set, rm, get}.

## Tunables (top of file)

    MANIFEST_NAME, NAME_FRAC, NAME_MIN, NAME_MAX, GAP, FALLBACK_WIDTH,
    DATALESS_PLACEHOLDER,
    COMMENT_STYLE, EZA_BASE

## Testing notes

- There is no real tty in CI/sandboxes; `shutil.get_terminal_size` falls back,
  and `COLUMNS=<n>` can simulate width. Verify no line exceeds the width by
  stripping ANSI and comparing visible length.
- For end-to-end tests, stub `eza` via the `EZA_BIN` env var with a fake script
  that emits `\U000f086f <ESC>[32m<name><ESC>[0m` lines. Use a Supplementary-
  PUA icon in the stub to catch the icon-range regression.
- Always confirm the no-comment case stays byte-identical to plain eza.

## Conventions for this codebase (owner preferences)

- Filenames use hyphens, not underscores, as word separators; shell scripts
  end in `.sh`.
- Files start with a terse magic line: `# comment: <under-60-char purpose>`.
- In docs and comments, minimize CAPS and emphasis.
- The owner uses two spaces after periods in prose (not enforced in code).

## Possible next steps (not yet built)

- `mv` subcommand to move a manifest entry when a file is renamed.
- Multi-directory args (`lsc dir1 dir2`) would need parsing eza section headers.
- `eza -l` long-format support would need different name-to-path mapping.
