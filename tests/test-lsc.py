#!/usr/bin/env python3
# comment: regression tests for lsc (run via run-tests.sh)

# These cover the features flagged in CLAUDE.md as regression-prone: byte-identical
# pass-through when nothing has a comment, Supplementary-PUA icon stripping,
# magic-line-beats-manifest precedence, and the no-line-ever-wraps width rule.
# The real eza is replaced by tests/fake-eza.py through the EZA_BIN env var.

import os
import re
import sys
import json
import subprocess
import tempfile
import shutil
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LSC = str(ROOT / "lsc.py")
STUB = str(HERE / "fake-eza.py")

try:
    os.chmod(STUB, 0o755)  # ensure the stub is executable however we're invoked
except OSError:
    pass

sys.path.insert(0, str(ROOT))
import lsc  # noqa: E402  (import after the sys.path tweak above)

ANSI_STYLING_RE = re.compile(r"\x1b\[[0-9;]*m")


def make_env(names, columns=120):
    env = os.environ.copy()
    env["EZA_BIN"] = STUB
    env["FAKE_EZA"] = "\n".join(names)
    env["COLUMNS"] = str(columns)  # shutil.get_terminal_size honors this
    env.pop("_eza_ignore", None)
    return env


def run_lsc(target, env):
    r = subprocess.run([sys.executable, LSC, target],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    return r.stdout


def run_stub(env):
    r = subprocess.run([sys.executable, STUB],
                       capture_output=True, text=True, env=env)
    return r.stdout


class LscTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _touch(self, name, body=""):
        (Path(self.dir) / name).write_text(body, encoding="utf-8")

    def _manifest(self, mapping):
        (Path(self.dir) / ".lsc-comments.json").write_text(
            json.dumps(mapping), encoding="utf-8")

    def test_passthrough_is_byte_identical(self):
        # No comments anywhere -> output must equal plain eza, byte for byte.
        names = ["alpha.txt", "beta.txt"]
        for n in names:
            self._touch(n)
        env = make_env(names)
        self.assertEqual(run_lsc(self.dir, env), run_stub(env))

    def test_supplementary_pua_icon_stripped(self):
        # The U+F086F icon must be stripped so the bare name can be recovered and
        # its manifest comment found.
        self._touch("notes.md")
        self._manifest({"notes.md": "meeting notes"})
        out = run_lsc(self.dir, make_env(["notes.md"]))
        self.assertIn("notes.md", out)
        self.assertIn("meeting notes", out)

    def test_magic_line_beats_manifest(self):
        self._touch("run.sh", "#!/bin/sh\n# comment: from magic line\n")
        self._manifest({"run.sh": "from manifest"})
        out = run_lsc(self.dir, make_env(["run.sh"]))
        self.assertIn("from magic line", out)
        self.assertNotIn("from manifest", out)

    def test_no_line_exceeds_width(self):
        # A long comment in a narrow terminal must be clipped so no visible
        # line (ANSI stripped) exceeds terminal width.
        self._touch("data.csv")
        self._manifest({"data.csv": "x" * 200})
        out = run_lsc(self.dir, make_env(["data.csv"], columns=40))
        for line in out.splitlines():
            visible = ANSI_STYLING_RE.sub("", line)
            self.assertLessEqual(len(visible), 40, repr(line))

    def test_directory_comment_shows_as_left_aligned_header(self):
        # A manifest "." entry prints first, left-aligned (no name/icon ahead
        # of it), in the comment style.
        self._touch("a.txt")
        self._touch("b.txt")
        self._manifest({".": "these are pleasant tools"})
        out = run_lsc(self.dir, make_env(["a.txt", "b.txt"]))
        first = out.splitlines()[0]
        self.assertEqual(ANSI_STYLING_RE.sub("", first), "these are pleasant tools")

    def test_set_dot_writes_directory_key(self):
        # `lsc --set . "..."` stores the caption under "." in this dir's manifest.
        self._touch("a.txt")
        r = subprocess.run([sys.executable, LSC, "--set", ".", "dir note"],
                           cwd=self.dir, capture_output=True, text=True,
                           env=make_env([]))
        self.assertEqual(r.returncode, 0, r.stderr)
        data = json.loads((Path(self.dir) / ".lsc-comments.json").read_text())
        self.assertEqual(data["."], "dir note")

    def test_rm_orphaned_entry_succeeds(self):
        # '--rm' must clear a manifest entry whose file no longer exists (deleted
        # or renamed); unlike '--set', it does not require the file to be present.
        self._manifest({"gone.txt": "old note"})
        r = subprocess.run([sys.executable, LSC, "--rm", "gone.txt"],
                           cwd=self.dir, capture_output=True, text=True,
                           env=make_env([]))
        self.assertEqual(r.returncode, 0, r.stderr)
        # the entry was the only one, so the manifest is removed entirely
        self.assertFalse((Path(self.dir) / ".lsc-comments.json").exists())

    def test_set_empty_comment_clears_entry(self):
        # An empty comment means "no comment": `--set FILE ""` removes the
        # entry (same as '--rm'), since "" and a missing entry are
        # indistinguishable in a listing. The now-empty manifest is cleaned up.
        self._touch("real.txt")
        self._manifest({"real.txt": "an existing note"})
        r = subprocess.run([sys.executable, LSC, "--set", "real.txt", ""],
                           cwd=self.dir, capture_output=True, text=True,
                           env=make_env([]))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((Path(self.dir) / ".lsc-comments.json").exists())

    def test_set_missing_file_is_refused(self):
        # '--set' refuses a nonexistent target (typo/wrong cwd) and writes no
        # manifest.
        r = subprocess.run([sys.executable, LSC, "--set", "nope.txt", "x"],
                           cwd=self.dir, capture_output=True, text=True,
                           env=make_env([]))
        self.assertEqual(r.returncode, 1)
        self.assertFalse((Path(self.dir) / ".lsc-comments.json").exists())

    def test_usage_error_exits_two(self):
        # Malformed invocation (wrong arg count) and conflicting action flags are
        # usage errors -> exit 2, distinct from a runtime failure (1). (The 1-vs-2
        # split is the exit-code contract documented at the top of main().)
        for argv in (["--set", "only-one-arg"],          # `--set` wants FILE + comment
                     ["--rm"],                            # `--rm` wants FILE
                     ["--get"],                           # `--get` wants FILE
                     ["--set", "f", "c", "--rm", "f"]):   # two action flags at once
            r = subprocess.run([sys.executable, LSC, *argv],
                               cwd=self.dir, capture_output=True, text=True,
                               env=make_env([]))
            self.assertEqual(r.returncode, 2, f"{argv}: {r.stderr}")

    def test_eza_returncode_is_propagated(self):
        # When eza runs but fails, lsc forwards eza's own returncode unchanged.
        env = make_env([])
        env["FAKE_EZA_RC"] = "3"
        r = subprocess.run([sys.executable, LSC, self.dir],
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertIn("simulated failure", r.stderr)

    def test_help_exits_zero_without_invoking_eza(self):
        env = make_env(["should-not-appear.txt"])
        r = subprocess.run([sys.executable, LSC, "--help"],
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("aligned comment column", r.stdout)
        self.assertNotIn("should-not-appear.txt", r.stdout)

    def test_version_exits_zero(self):
        r = subprocess.run([sys.executable, LSC, "--version"],
                           capture_output=True, text=True, env=make_env([]))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertRegex(r.stdout.strip(), r"^lsc \d+\.\d+\.\d+$")

    def test_dataless_placeholder_is_right_aligned(self):
        # The placeholder is pushed to the terminal's right edge, so the
        # visible line fills the full width and ends with the placeholder.
        ph = lsc.UNFETCHED_ICLOUD_PLACEHOLDER
        self._touch("clip.mov")
        self._manifest({"clip.mov": ph})  # equals the placeholder sentinel
        COLS = 60
        out = run_lsc(self.dir, make_env(["clip.mov"], columns=COLS))
        line = next(l for l in out.splitlines()
                    if ph in ANSI_STYLING_RE.sub("", l))
        visible = ANSI_STYLING_RE.sub("", line)
        self.assertEqual(len(visible), COLS)
        self.assertTrue(visible.endswith(ph))

    def test_fetch_icloud_flag_is_consumed(self):
        # Both the long flag and the '--fetch' shorthand must be stripped before
        # eza sees them; output is unaffected.
        names = ["a.txt", "b.txt"]
        for n in names:
            self._touch(n)
        env = make_env(names)
        for flag in ("--fetch-icloud", "--fetch"):
            r = subprocess.run([sys.executable, LSC, flag, self.dir],
                               capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout, run_lsc(self.dir, env), flag)


class DatalessTests(unittest.TestCase):
    # The evicted-iCloud guard. is_dataless is monkeypatched because real
    # dataless files (and the SF_DATALESS st_flags bit) only exist on macOS, so
    # these run identically on a Linux CI box.

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self._orig = lsc.is_dataless

    def tearDown(self):
        lsc.is_dataless = self._orig
        self._tmp.cleanup()

    def _make(self):
        path = Path(self.dir) / "field-notes.md"
        path.write_text("# comment: from magic line\n", encoding="utf-8")
        (Path(self.dir) / ".lsc-comments.json").write_text(
            json.dumps({"field-notes.md": "from manifest"}), encoding="utf-8")
        return str(path)

    def test_evicted_file_skips_magic_uses_manifest(self):
        path = self._make()
        lsc.is_dataless = lambda p: True
        self.assertEqual(
            lsc.get_effective_comment(path, fetch_icloud=False), "from manifest")

    def test_evicted_file_without_comment_shows_placeholder(self):
        # No manifest entry and the file is not read -> the placeholder fills
        # the column instead of leaving it blank.
        path = Path(self.dir) / "vacation.mov"
        path.write_text("# comment: unreachable while evicted\n",
                        encoding="utf-8")
        lsc.is_dataless = lambda p: True
        self.assertEqual(
            lsc.get_effective_comment(str(path), fetch_icloud=False),
            lsc.UNFETCHED_ICLOUD_PLACEHOLDER)

    def test_fetch_icloud_reads_magic(self):
        path = self._make()
        lsc.is_dataless = lambda p: True
        self.assertEqual(
            lsc.get_effective_comment(path, fetch_icloud=True), "from magic line")

    def test_local_file_always_reads_magic(self):
        path = self._make()
        lsc.is_dataless = lambda p: False
        self.assertEqual(
            lsc.get_effective_comment(path, fetch_icloud=False), "from magic line")


EZA = shutil.which("eza")


@unittest.skipUnless(EZA, "real eza not installed")
class IntegrationTests(unittest.TestCase):
    # Runs lsc against the real eza binary to catch output-format drift the
    # stub cannot. Skipped automatically when eza is not on PATH, so the suite
    # still passes without eza (e.g. on a Python-only CI runner).

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _env(self, columns=120):
        env = os.environ.copy()
        env.pop("EZA_BIN", None)   # use the real eza on PATH, not the stub
        env.pop("FAKE_EZA", None)
        env["COLUMNS"] = str(columns)
        return env

    def test_real_eza_listing_and_precedence(self):
        (Path(self.dir) / "report.txt").write_text("data\n", encoding="utf-8")
        (Path(self.dir) / "run.sh").write_text(
            "#!/bin/sh\n# comment: from magic line\n", encoding="utf-8")
        (Path(self.dir) / ".lsc-comments.json").write_text(
            json.dumps({"report.txt": "quarterly bananas",
                        "run.sh": "from manifest"}), encoding="utf-8")
        r = subprocess.run([sys.executable, LSC, self.dir],
                           capture_output=True, text=True, env=self._env())
        self.assertEqual(r.returncode, 0, r.stderr)
        plain = ANSI_STYLING_RE.sub("", r.stdout)
        # filenames survive real icon + ANSI stripping
        self.assertIn("report.txt", plain)
        self.assertIn("run.sh", plain)
        # manifest comment shows; an in-file magic line wins over the manifest
        self.assertIn("quarterly bananas", plain)
        self.assertIn("from magic line", plain)
        self.assertNotIn("from manifest", plain)

    def test_real_eza_no_line_exceeds_width(self):
        (Path(self.dir) / "data.csv").write_text("x\n", encoding="utf-8")
        (Path(self.dir) / ".lsc-comments.json").write_text(
            json.dumps({"data.csv": "y" * 200}), encoding="utf-8")
        cols = 50
        r = subprocess.run([sys.executable, LSC, self.dir],
                           capture_output=True, text=True,
                           env=self._env(columns=cols))
        self.assertEqual(r.returncode, 0, r.stderr)
        for line in r.stdout.splitlines():
            self.assertLessEqual(len(ANSI_STYLING_RE.sub("", line)), cols, repr(line))


class EzaOptsTests(unittest.TestCase):
    # LSC_EZA_OPTS: a user flag replaces a matching default in place (by option
    # identity, aliases included); unrelated flags append; '--oneline' is forced.

    def setUp(self):
        self._saved = os.environ.get("LSC_EZA_OPTS")

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("LSC_EZA_OPTS", None)
        else:
            os.environ["LSC_EZA_OPTS"] = self._saved

    def _opts(self, value=None):
        if value is None:
            os.environ.pop("LSC_EZA_OPTS", None)
        else:
            os.environ["LSC_EZA_OPTS"] = value
        return lsc.eza_opts()

    def test_defaults_when_unset(self):
        self.assertEqual(self._opts(), lsc.EZA_DEFAULTS)

    def test_oneline_is_required_and_separate(self):
        self.assertEqual(lsc.EZA_REQUIRED, ["--oneline"])

    def test_override_replaces_default_in_place_no_duplicate(self):
        opts = self._opts("--icons=never")
        self.assertIn("--icons=never", opts)
        self.assertNotIn("--icons=always", opts)
        self.assertEqual(sum(o.split("=")[0] == "--icons" for o in opts), 1)
        self.assertIn("--classify", opts)  # other defaults intact

    def test_alias_spelling_matches_default(self):
        opts = self._opts("--colour=never -F=never")  # UK spelling + short -F
        self.assertNotIn("--color=always", opts)
        self.assertIn("--colour=never", opts)
        self.assertNotIn("--classify", opts)
        self.assertIn("-F=never", opts)

    def test_unrelated_flag_is_appended(self):
        opts = self._opts("--git")
        self.assertEqual(opts[:len(lsc.EZA_DEFAULTS)], lsc.EZA_DEFAULTS)
        self.assertEqual(opts[-1], "--git")


if __name__ == "__main__":
    unittest.main(verbosity=2)
