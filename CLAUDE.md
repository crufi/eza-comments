---
# comment: project context for the lsc comment-column tool
---
# CLAUDE.md

Maintainer notes for editing `lsc.py`. **Read `README.md` first** — it covers
what lsc is, how it installs, the flags, and the env vars (`LSC_EZA_OPTS`,
`LSC_FETCH_ICLOUD`, …). This file deliberately does *not* repeat that; it holds
only what a user-facing README shouldn't: the rationale behind the design, the
bugs that are easy to reintroduce, and a map of the code. When behavior changes,
update the README (the source of truth for behavior) and touch this file only
for design/gotcha changes.

`lsc` is one dependency-free Python file (`wcwidth` used only if importable),
plus thin shell wrappers and a Makefile.

## Where comments come from (the code-level view; README has the user version)

1. An in-file magic line in the first 50 lines of a text file:
   `(?i)^\s*(?://|#|--|;)\s*comment:\s*(.*)$`. Binary / non-UTF-8 files are
   skipped (null-byte probe + decode guard).
2. A per-directory JSON manifest, `.lsc-comments.json`, mapping bare filename
   to comment string.

The magic line wins over the manifest. `--set`/`--rm` operate on the manifest only;
they warn (stderr) but still act when a magic line shadows the manifest.

The manifest key `.` (constant `DIR_KEY`) is special: it is the directory's own
caption, not a file. The lister reads `load_manifest(base).get(DIR_KEY)` and, if
present, emits it as the first output line — left-aligned at column zero, in the
comment style, above the listing. It is manifest-only (a directory has no head
to scan) and is set with `lsc --set . "..."` (which `os.path.split` resolves to
`name == "."` in that directory's manifest, so no special-casing in `cmd_set`).

The same `.` caption does double duty: when a *listed entry* is a directory,
`resolve_comment` shows that subdirectory's own `.` caption as its row comment
(`get_dir_caption_value`). This is one level deep — the `--oneline` listing is
flat, so each line is one immediate child and there is no recursion.

A directory's comment comes **only** from its own `.` caption; a parent
manifest's entry for a subdirectory is ignored (parent entries are for files).
This was a deliberate simplification of an earlier "subdir caption beats parent
entry" precedence — two sources for one directory was confusing, and caption-only
means the comment always travels with the directory. Consequences in the code:
`cmd_set_rm` redirects a directory target to its own manifest (`--set DIR` ==
`--set DIR/.`, so you must be able to write `DIR` itself, not just its parent),
and `warn_if_shadowed` is back to the magic-line case only — there is no
parent-entry-vs-caption shadowing left to warn about. `get_dir_caption_value`
honors the no-download rule: it skips an evicted manifest unless `--fetch` is
set.

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
- **`--set` refuses if the file does not exist** (catches typos / wrong cwd).
- **`--set FILE ""` (empty comment) removes the entry**, same as `--rm`, since an
  empty string and a missing entry are indistinguishable in a listing; this also
  keeps the manifest from accumulating no-op `""` entries. The store-vs-delete
  choice is therefore keyed on the comment being empty, not on which flag was
  used. (One deliberate asymmetry: `--set FILE ""` is silent when there was no
  entry, while `--rm` warns; `--set ""` reads as idempotent "ensure no comment".)
- **Layout is terminal-width adaptive.** Name column scales to the terminal,
  comments clip with an ellipsis so no line ever wraps. When stdout is not a
  tty (piped), width falls back to `FALLBACK_WIDTH` and output is byte-
  identical to plain eza when no comments exist.
- **Recency highlight stores its timestamp in the manifest, not a side file.**
  A comment changed within `HILITE_SECS` is drawn in `HILITE_STYLE` (on by
  default). The set-time lives *in the manifest entry*, which is why the value
  schema grew from a bare string to `{"text": ..., "ts": ...}` (an earlier plan
  used an external `~/.local/state` dict — rejected so nothing lives outside the
  directory tree; the timestamp travels with the folder like the comment does).
  The `ts` is a human-readable local ISO-8601 string (`isoformat(timespec=
  "seconds")`), deliberately not epoch nanos, so a hand-inspected manifest stays
  legible. Any legacy bare-string entries are still read (`entry_text`/`entry_ts`) and
  simply never highlight, so old manifests keep working. A magic comment has no
  stored time; its freshness comes from the file mtime, since editing the file
  is the only way to change it. On-by-default is safe for the byte-identical
  guarantee because the highlight only ever recolors a row that already has a
  comment — a no-comment listing is untouched either way.

## Gotchas that caused bugs (regression-prone areas)

- **Nerd Font icons span three PUA ranges.** `get_clean_filename` strips the leading
  icon glyph; `is_pua` must cover the BMP PUA (U+E000–U+F8FF) AND both Supplementary
  areas (U+F0000–U+FFFFD, U+100000–U+10FFFD). A BMP-only check silently failed
  on real eza output (icons like U+F086F), producing mangled names and missing
  comments. Test with a Supplementary-PUA icon, not just U+E0A0.
- **eza filenames must be bare for lookups to work.** `get_effective_comment` opens the
  name eza printed. If eza quotes spaced names (`'My File.txt'`) the open
  fails. `--no-quotes` (in `EZA_DEFAULTS`) keeps them bare; overriding it via
  `LSC_EZA_OPTS` loses comments on spaced names.
- **ANSI-aware truncation.** Never slice a colored line at a visible-column
  count without preserving escape sequences and appending a reset, or color
  bleeds / escapes get cut mid-sequence. See `truncate_ansi` and `clip_text`.
- **Width math is icon-inclusive.** Column positions are measured on the full
  visible line (icon + name + classify char), so truncation and padding share
  one origin. Mixing name-space and line-space measurements misaligns the
  column.
- **Comment text and its recency must come from one precedence path.**
  `resolve_comment` returns `(text, recent)` together so the highlighted comment
  is always the one actually shown; `get_effective_comment` is just its `[0]`.
  If you add a new comment source, extend `resolve_comment` (not a parallel
  freshness lookup), or text and highlight can disagree. The render loop folds
  the `hilite` on/off switch into the per-row `recent` flags up front, so
  `style_comment` stays style-agnostic.
- **Write failures must not raise.** `save_manifest` returns a bool and cleans
  up its temp file on failure; `cmd_set`/`cmd_rm` report a clean error and exit
  non-zero. A read-only directory must not produce a traceback.
- **Reading a file triggers iCloud downloads.** The magic-comment probe opens
  every listed file's head; for an evicted ("Optimize Mac Storage") file that
  read forces macOS to materialize it from iCloud, which is slow and uses data.
  The listing therefore skips the probe for dataless files (`is_dataless`, the
  `SF_DATALESS` st_flags bit) unless `--fetch-icloud` / `--fetch` /
  `LSC_FETCH_ICLOUD` is
  set, falling back to the manifest (or `DATALESS_PLACEHOLDER` when the manifest
  has no entry). Do not move the probe ahead of this guard,
  and do not assume `stat` is enough — it is the open/read that downloads, not
  the stat. `st_flags` is macOS-only, so the guard no-ops elsewhere.

## Key functions

- `resolve_comment(path, fetch_icloud=True)` — the core resolver: returns
  `(text, recent)`, deciding the shown comment and its freshness on one
  precedence path (a directory: its own `.` caption only; a file: magic line >
  manifest).
- `get_effective_comment(path, fetch_icloud=True)` — `resolve_comment(...)[0]`,
  the text-only view used by `--get`. The lister passes `fetch_icloud=False`;
  `--set`/`--rm`/`--get` keep the default.
- `get_magic_comment` / `get_manifest_comment` — the two sources.
- `entry_text` / `entry_ts` — read a manifest value that is either a bare string
  (legacy) or `{"text": ..., "ts": ...}`; `cmd_set_rm` writes only the latter.
- `now_ts` / `ts_is_recent` / `mtime_is_recent` — current local time (overridable
  by `LSC_NOW` for tests) and the two within-`HILITE_SECS` freshness checks.
- `get_dir_caption_value` — raw manifest value for a directory's own `.` caption,
  used both as its header when listed directly and as its row comment in the
  parent; skips an evicted manifest unless fetching.
- `is_dataless` — macOS SF_DATALESS check; gates the magic-comment probe so a
  listing never forces an iCloud download.
- `search_head` — binary-guarded, islice-capped (50 lines) regex scan.
- `load_manifest` / `save_manifest` — JSON read / atomic write (temp+rename,
  auto-deletes when empty, returns False on failure).
- `get_clean_filename` / `is_pua` — recover the bare filename from an eza line.
- `truncate_ansi` / `clip_text` — width-bounded, ANSI-safe cutting.
- `base_dir` — resolve `lsc DIR` names against DIR (single-dir case only).
- `cmd_set` / `cmd_rm` / `cmd_get` — manifest CRUD; dispatched in `main` on
  the `--set` / `--rm` / `--get` flags (not subcommands, so a path named
  `set`/`rm`/`get` still lists). A directory target is redirected to its own
  manifest's `.` key (`--set DIR` == `--set DIR/.`).
- `warn_if_shadowed` — on `--set`/`--rm`, warns when a file's in-file magic line
  will outrank the manifest entry in the listing (no-op for a directory).

## Tunables (top of file)

    MANIFEST_NAME, NAME_FRAC, NAME_MIN, NAME_MAX, GAP, FALLBACK_WIDTH,
    DATALESS_PLACEHOLDER,
    COMMENT_STYLE, HILITE_STYLE, HILITE_SECS, HILITE_RECENT,
    EZA_REQUIRED, EZA_DEFAULTS, EZA_OPT_KEY

`COMMENT_STYLE`, `HILITE_STYLE`, `HILITE_SECS`, and `HILITE_RECENT` each read an
`LSC_*` env override at import (so they can be tuned without editing the file);
the literal beside them is the fallback default.

## Testing notes

- There is no real tty in CI/sandboxes; `shutil.get_terminal_size` falls back,
  and `COLUMNS=<n>` can simulate width. Verify no line exceeds the width by
  stripping ANSI and comparing visible length.
- For end-to-end tests, stub `eza` via the `EZA_BIN` env var with a fake script
  that emits `\U000f086f <ESC>[32m<name><ESC>[0m` lines. Use a Supplementary-
  PUA icon in the stub to catch the icon-range regression.
- Always confirm the no-comment case stays byte-identical to plain eza.
- Recency is time-dependent; pin "now" with `LSC_NOW` (an ISO-8601 string) so
  highlight tests are deterministic. Magic-comment freshness keys off file
  mtime, so use `os.utime` to age a file for the not-recent case. Assert on the
  `HILITE_STYLE` escape (`\x1b[<style>m`) rather than a hardcoded color.

## Conventions for this codebase (owner preferences)

- Filenames use hyphens, not underscores, as word separators; shell scripts
  end in `.sh`.
- Files start with a terse magic line: `# comment: <under-60-char purpose>`.
- In docs and comments, minimize all-caps/emphasis.

## Possible next steps (not yet built)

- `lsc --mv` to move a manifest entry when a file is renamed (but feels like overkill).
- Multi-directory args (`lsc dir1 dir2`) would need parsing eza section headers.
- `eza -l` long-format support would need different name-to-path mapping.
