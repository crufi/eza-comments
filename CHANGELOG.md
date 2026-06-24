<!-- comment: version history, keep-a-changelog format -->

# Changelog

All notable changes to `lsc` are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-06-23

First public release. `lsc` adds an aligned, per-file comment column to
[`eza`](https://github.com/eza-community/eza) output — colors and Nerd Font
icons intact, no dependencies. A single Python 3.8+ script runs `eza` once and
annotates the result. The idea is borrowed from the original Macintosh Finder
(Horn and Capps, 1984).

### Added

- Per-file comments from two sources, magic line winning over manifest: an
  in-file `comment:` line near the top of a text file (markers `//`, `#`,
  `--`, `;`), or a per-directory `.lsc-comments.json` manifest for everything
  else, including binaries. Both are ordinary file content, so they survive
  iCloud sync, file eviction, editor atomic-saves, and `rsync`.
- Terminal-width-aware layout: the name column grows on wide terminals and
  clips sooner on narrow ones; the comment column starts past the longest name
  and clips with an ellipsis so no line ever wraps. With no comments present,
  output is byte-identical to plain `eza`.
- Recently-changed highlighting: a comment set or edited within the last 60
  seconds draws in a muted gold. On by default; `--no-hilite-recent` /
  `--hilite-recent` and `LSC_HILITE_RECENT` control it.
- Directory captions: a manifest entry keyed `.` captions a folder, printed as
  a header above the listing and shown in the parent's listing.
- iCloud awareness on macOS: evicted files are not read by default, so listing
  never forces a download; they show a manifest comment or a `(not downloaded)`
  marker. `--fetch-icloud` / `--fetch` reads them anyway.
- Comment management: `--set`, `--rm`, `--get`, and the `setcomm` / `rmcomm` /
  `getcomm` shell wrappers.
- Pass-through to `eza`: non-`lsc` flags are forwarded; `LSC_EZA_OPTS`
  overrides the defaults, replacing conflicting flags in place.
- Install paths: Homebrew tap (`brew install crufi/tap/lsc`) and `make install`
  from source. Shell functions in `lsc.sh`.
- Tunables at the top of `lsc.py`, several with environment-variable overrides.

[Unreleased]: https://github.com/crufi/eza-comments/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/crufi/eza-comments/releases/tag/v0.1.0
