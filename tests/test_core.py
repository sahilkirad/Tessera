from __future__ import annotations

import ast
import io
import os
import random
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import helpers
from helpers import make_repo, root_of

import _core
from _core import (
    HARD_CAP, IgnoreRules, PathError, UsageError, estimate_tokens, find_repo_files,
    footer, next_budget, padded, read_text, resolve_budget, safe_resolve,
)


def scan(files, extra_rules=None):
    """Return (kept files, warnings) for a synthetic repo."""
    with make_repo(files) as tmp:
        root = root_of(tmp)
        warnings: list = []
        found = find_repo_files(root, IgnoreRules.from_root(root), warnings)
        return found, warnings


class IgnoreRuleTests(unittest.TestCase):
    def test_defaults_skip_caches_and_vcs_with_warning(self):
        found, warns = scan({
            "a.py": "x=1", "__pycache__/a.py": "x", ".git/h.py": "x", "pkg/__pycache__/b.py": "x",
            "node_modules/n.py": "x", "x.egg-info/e.py": "x",
        })
        self.assertEqual(found, ["a.py"])
        text = " | ".join(warns)
        self.assertIn("skipped 2 dirs named __pycache__", text)
        self.assertIn("skipped dir: .git/", text)
        self.assertIn("skipped dir: node_modules/", text)
        self.assertIn("skipped dir: x.egg-info/", text)

    def test_gitignore_patterns(self):
        found, warns = scan({
            ".gitignore": "# comment\n\n*.gen.py\ngenerated/\n/top.py\ndocs/**/skip.py\n",
            "ok.py": "", "a.gen.py": "", "generated/g.py": "", "top.py": "",
            "sub/top.py": "", "docs/x/y/skip.py": "", "docs/keep.py": "",
        })
        self.assertEqual(found, ["docs/keep.py", "ok.py", "sub/top.py"])
        self.assertTrue(any("generated/" in w for w in warns))

    def test_negation_and_prunerignore_override(self):
        found, _ = scan({
            ".gitignore": "*.py\n!keep.py\n",
            "keep.py": "", "drop.py": "",
            ".prunerignore": "keep.py\n!drop.py\n",
        })
        self.assertEqual(found, ["drop.py"])

    def test_anchored_vs_unanchored_dir(self):
        found, _ = scan({
            ".gitignore": "/vendor/\ntmp/\n",
            "vendor/v.py": "", "a/vendor/v.py": "", "tmp/t.py": "", "a/tmp/t.py": "",
        })
        self.assertEqual(found, ["a/vendor/v.py"])

    def test_double_star_and_question_mark(self):
        found, _ = scan({
            ".gitignore": "**/gen/\nf?.py\na/**/z.py\n",
            "gen/x.py": "", "p/gen/x.py": "", "f1.py": "", "f12.py": "", "a/z.py": "",
            "a/b/c/z.py": "", "a/b/y.py": "",
        })
        self.assertEqual(found, ["a/b/y.py", "f12.py"])

    def test_virtualenv_detected_by_pyvenv_cfg_not_name(self):
        found, warns = scan({
            "myenv/pyvenv.cfg": "home = x", "myenv/lib.py": "x=1",
            "venv/real.py": "x=1", "env/real.py": "x=1", "pkg/coverage/c.py": "x=1",
            "pkg/build/b.py": "x=1", "src.py": "x=1",
        })
        self.assertEqual(found, ["env/real.py", "pkg/build/b.py", "pkg/coverage/c.py", "src.py", "venv/real.py"])
        self.assertTrue(any("myenv/" in w and "virtualenv" in w for w in warns))

    def test_build_and_dist_only_at_root(self):
        found, warns = scan({"build/a.py": "", "dist/b.py": "", "pkg/dist/c.py": "", "pkg/build/d.py": ""})
        self.assertEqual(found, ["pkg/build/d.py", "pkg/dist/c.py"])
        self.assertTrue(any("build/" in w for w in warns) and any("dist/" in w for w in warns))

    def test_big_and_binary_files_warn(self):
        found, warns = scan({
            "ok.py": "x=1\n", "big.py": b"x = 1\n" * 200_000, "bin.py": b"a = 1\x00\x00\n",
        })
        self.assertEqual(found, ["ok.py"])
        self.assertIn("skipped file: big.py (over 1 MB)", warns)
        self.assertIn("skipped file: bin.py (binary)", warns)

    def test_secret_named_py_is_skipped(self):
        found, warns = scan({"secrets.py": "K='x'", "ok.py": ""})
        self.assertEqual(found, ["ok.py"])
        self.assertTrue(any("ignore rules" in w for w in warns))

    def test_only_py_files_sorted(self):
        found, _ = scan({"b.py": "", "a.py": "", "c.txt": "", "z/y.py": "", "Z.py": ""})
        self.assertEqual(found, ["Z.py", "a.py", "b.py", "z/y.py"])

    def test_symlink_dir_not_followed(self):
        with make_repo({"real/a.py": "x=1"}) as tmp:
            root = root_of(tmp)
            try:
                os.symlink(os.path.join(root, "real"), os.path.join(root, "loop"), target_is_directory=True)
                os.symlink(root, os.path.join(root, "real", "up"), target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks not permitted")
            warns: list = []
            found = find_repo_files(root, None, warns)
            self.assertEqual(found, ["real/a.py"])
            self.assertTrue(any("(symlink)" in w for w in warns))


class SafeResolveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = make_repo({
            "a.py": "x=1", "pkg/b.py": "y=2", ".env": "K=1", "creds/id_rsa": "k",
            "key.pem": "k", "build/x.py": "z=1", "__pycache__/c.py": "",
            ".gitignore": "hidden/\n", "hidden/h.py": "h=1",
        })
        self.root = root_of(self.tmp)
        self.addCleanup(self.tmp.cleanup)

    def test_inside_ok(self):
        self.assertEqual(safe_resolve(self.root, "pkg/b.py"), Path(self.root, "pkg", "b.py"))
        self.assertEqual(safe_resolve(self.root, os.path.join(self.root, "a.py")), Path(self.root, "a.py"))

    def test_rejects_traversal_and_outside(self):
        with self.assertRaises(PathError):
            safe_resolve(self.root, "../outside.py")
        with self.assertRaises(PathError):
            safe_resolve(self.root, str(Path(self.root).parent / "other.py"))

    def test_rejects_ignored_secret_and_missing(self):
        for bad in (".env", "key.pem", "creds/id_rsa", "build/x.py", "__pycache__/c.py", "hidden/h.py", "nope.py"):
            with self.subTest(path=bad), self.assertRaises(PathError):
                safe_resolve(self.root, bad)


class ReadTextTests(unittest.TestCase):
    def read(self, data: bytes) -> str:
        with make_repo({"f.py": data}) as tmp:
            return read_text(Path(tmp, "f.py"))

    def test_bom_crlf_and_lone_cr(self):
        self.assertEqual(self.read(b"\xef\xbb\xbfa=1\r\nb=2\rc=3\n"), "a=1\nb=2\nc=3\n")

    def test_bad_bytes_replaced(self):
        self.assertIn("�", self.read(b"a = '\xff'\n"))

    def test_form_feed_keeps_ast_line_numbers(self):
        src = "x = 1\n\x0c\ndef f():\r\n    pass\r\rdef g():\n    pass\n"
        text = self.read(src.encode("utf-8"))
        lines = text.split("\n")
        for node in ast.parse(text).body:
            if isinstance(node, ast.FunctionDef):
                self.assertTrue(lines[node.lineno - 1].startswith("def " + node.name))
        self.assertNotEqual(len(text.splitlines()), len(lines) - 1)


class EstimateTests(unittest.TestCase):
    def test_empty_and_nonempty(self):
        self.assertEqual(estimate_tokens(""), 0)
        for text in (" ", "\t", "a", "1", "(", "é"):
            self.assertGreater(estimate_tokens(text), 0, repr(text))

    def test_prefix_monotonic(self):
        rng = random.Random(7)
        alphabet = "abcXYZ_ 09\n\t(){}.é"
        for _ in range(60):
            text = "".join(rng.choice(alphabet) for _ in range(80))
            counts = [estimate_tokens(text[:i]) for i in range(len(text) + 1)]
            self.assertEqual(counts, sorted(counts), text)

    def test_identifier_splitting(self):
        self.assertEqual(estimate_tokens("abcd"), 1)
        self.assertEqual(estimate_tokens("applyDiscount"), 4)
        self.assertEqual(estimate_tokens("apply_discount"), 5)
        self.assertGreater(estimate_tokens("a" * 400), estimate_tokens("a" * 40))

    def test_padded_margin(self):
        self.assertEqual(padded(100), 110)
        self.assertGreaterEqual(padded(1), 2)


class BudgetTests(unittest.TestCase):
    def test_precedence(self):
        self.assertEqual(resolve_budget(None, None), (2000, "default", []))
        self.assertEqual(resolve_budget(None, "bug"), (3000, "task", []))
        self.assertEqual(resolve_budget(1500, "bug"), (1500, "explicit", []))

    def test_clamp_and_errors(self):
        budget, source, warns = resolve_budget(99999, None)
        self.assertEqual((budget, source), (HARD_CAP, "clamped"))
        self.assertEqual(len(warns), 1)
        with self.assertRaises(UsageError):
            resolve_budget(None, "huge")
        with self.assertRaises(UsageError):
            resolve_budget(0, None)

    def test_next_budget_ladder(self):
        chain = [next_budget(b) for b in (500, 1000, 2000, 3000, 4000, 5000, 7500, 8000, 9000)]
        self.assertEqual(chain, [1000, 2000, 3000, 4000, 5000, 7500, 8000, None, None])


class OutputTests(unittest.TestCase):
    def test_footer_caps(self):
        text = footer(["o%d" % i for i in range(20)], ["w%d" % i for i in range(7)])
        omitted, warnings = text.split("\n")
        self.assertTrue(omitted.endswith("o14; +5 more"))
        self.assertEqual(warnings, "WARNINGS: w0; w1; w2; w3; w4; +2 more")

    def test_footer_omits_empty_lines(self):
        self.assertEqual(footer([], []), "")
        self.assertEqual(footer(["x"], []), "OMITTED: x")
        self.assertEqual(footer([], ["w"]), "WARNINGS: w")

    def test_setup_stdout_tolerates_plain_streams(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            _core.setup_stdout()
            print("héllo")
        self.assertIn("héllo", buf.getvalue())

    def test_unicode_survives_cp1252_console(self):
        code = "import _core; _core.setup_stdout(); print('naïve ✓ 名前')"
        env = dict(os.environ, PYTHONPATH=str(helpers.SCRIPTS), PYTHONIOENCODING="cp1252")
        proc = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.decode("utf-8").strip(), "naïve ✓ 名前")


if __name__ == "__main__":
    unittest.main()
