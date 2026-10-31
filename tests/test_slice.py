from __future__ import annotations

import io
import unittest
from collections import Counter
from contextlib import redirect_stdout
from pathlib import Path

import helpers
from fixtures import FIXTURE
from helpers import make_repo, root_of

import slice as slice_cli
from _core import read_text
from _index import parse_file, slice_report, split_target

AMBIGUOUS = (
    "class A:\n    def validate(self):\n        return 1\n\n\n"
    "class B:\n    def validate(self):\n        return 2\n\n\n"
    "class C:\n    def validate(self):\n        return 3\n"
)
LONG = "def long_one():\n" + "".join("    x%d = %d\n" % (i, i) for i in range(30)) + "    return 0\n"
FILES = dict(FIXTURE, **{"amb.py": AMBIGUOUS, "long.py": LONG})


def run(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = slice_cli.main(argv)
    return code, buf.getvalue()


class SplitTargetTests(unittest.TestCase):
    def test_split(self):
        self.assertEqual(split_target("a/b.py"), ("a/b.py", None))
        self.assertEqual(split_target("a/b.py:Cls.m"), ("a/b.py", "Cls.m"))
        self.assertEqual(split_target("a/b.py:40-88"), ("a/b.py", "40-88"))
        self.assertEqual(split_target("C:\\repo\\a.py"), ("C:\\repo\\a.py", None))
        self.assertEqual(split_target("C:/repo/a.py:f"), ("C:/repo/a.py", "f"))


class SymbolProperty(unittest.TestCase):
    def check_file(self, path: Path, rel: str):
        text = read_text(path)
        original = text.split("\n")
        fi = parse_file(rel, text, len(text), [])
        self.assertTrue(fi.parse_ok, rel)
        counts = Counter(s.qualname for s in fi.symbols)
        checked = 0
        for sym in fi.symbols:
            if counts[sym.qualname] != 1:
                continue
            out, omitted, _ = slice_report(path, rel, sym.qualname, max_lines=10 ** 6)
            head, *body = out.split("\n")
            self.assertEqual(head, "SLICE %s::%s L%d-%d" % (rel, sym.qualname, sym.start, sym.end))
            self.assertEqual(body, original[sym.start - 1:sym.end], (rel, sym.qualname))
            self.assertEqual(omitted, [])
            checked += 1
        return checked

    def test_every_symbol_in_fixture_and_scripts(self):
        total = 0
        with make_repo(FILES) as tmp:
            for rel in ("shop/models.py", "shop/billing.py", "uni.py", "app.py", "long.py"):
                total += self.check_file(Path(tmp, *rel.split("/")), rel)
        for path in sorted(helpers.SCRIPTS.glob("*.py")):
            total += self.check_file(path, path.name)
        self.assertGreater(total, 80)


class SliceCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = make_repo(FILES)
        cls.root = root_of(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def slice(self, target, *extra):
        return run([target, "--root", self.root, *extra])

    def test_symbol_exact_with_decorators_and_indent(self):
        code, out = self.slice("shop/models.py:Cart.total")
        self.assertEqual(code, 0)
        self.assertEqual(out, "SLICE shop/models.py::Cart.total L25-28\n"
                              "    @property\n    def total(self) -> float:\n"
                              "        def helper(): return 1\n        return helper()\n")

    def test_name_without_class_resolves_when_unique(self):
        _, out = self.slice("shop/models.py:documented")
        self.assertTrue(out.startswith("SLICE shop/models.py::documented L45-47\n"))

    def test_range_mode_exact(self):
        _, out = self.slice("shop/models.py:42-43")
        self.assertEqual(out, "SLICE shop/models.py L42-43\ndef free(x): return x\n\n")

    def test_range_clamp_and_out_of_range_and_bad(self):
        _, out = self.slice("shop/models.py:46-999")
        self.assertIn("SLICE shop/models.py L46-47", out)
        self.assertIn("WARNINGS: range clamped to 47 lines", out)
        self.assertEqual(self.slice("shop/models.py:500-600"), (0, "OUT OF RANGE: shop/models.py has 47 lines\n"))
        self.assertEqual(self.slice("shop/models.py:9-3")[0], 2)
        self.assertEqual(self.slice("shop/models.py:0-3")[0], 2)

    def test_range_works_on_unparsable_file(self):
        code, out = self.slice("broken.py:1-2")
        self.assertEqual(code, 0)
        self.assertEqual(out, "SLICE broken.py L1-2\ndef oops(:\n    pass\n")

    def test_context_lines_and_header(self):
        _, out = self.slice("shop/models.py:free", "--context", "2")
        lines = out.split("\n")
        self.assertEqual(lines[0], "SLICE shop/models.py::free L42-42 (context 2: L40-44)")
        self.assertEqual(lines[1:6], ["", "", "def free(x): return x", "", ""])

    def test_with_class_prepends_header(self):
        _, out = self.slice("shop/models.py:Cart.add", "--with-class")
        lines = out.split("\n")
        self.assertEqual(lines[0], "SLICE shop/models.py::Cart.add L21-23 (+ class header L10)")
        self.assertEqual(lines[1], "class Cart:")
        self.assertEqual(lines[2], "    def add(self, item, qty: int = 1) -> None:")

    def test_with_class_on_plain_function_is_harmless(self):
        _, out = self.slice("shop/models.py:free", "--with-class")
        self.assertTrue(out.startswith("SLICE shop/models.py::free L42-42\n"))

    def test_ambiguous_message(self):
        code, out = self.slice("amb.py:validate")
        self.assertEqual(code, 0)
        self.assertEqual(out, "AMBIGUOUS: 'validate' matches 3 symbols: A.validate (L2), "
                              "B.validate (L7), C.validate (L12); use the full qualname\n")
        self.assertIn("SLICE amb.py::B.validate L7-8", self.slice("amb.py:B.validate")[1])

    def test_not_found_with_closest(self):
        _, out = self.slice("shop/models.py:documentd")
        self.assertEqual(out, "NOT FOUND: 'documentd'. Closest in this file: documented\n")
        _, none = self.slice("shop/models.py:zzzzzz")
        self.assertTrue(none.startswith("NOT FOUND: 'zzzzzz'. Closest in this file: (none"))

    def test_truncation_marker(self):
        _, out = self.slice("long.py:long_one", "--max-lines", "10")
        lines = out.rstrip("\n").split("\n")
        marker = "TRUNCATED at 10 lines; use slice long.py:11-32 for the rest"
        self.assertEqual(lines[0], "SLICE long.py::long_one L1-32")
        self.assertEqual(lines[1:11], LONG.split("\n")[:10])
        self.assertEqual(lines[11], marker)
        self.assertEqual(lines[12], "OMITTED: " + marker)
        _, whole = self.slice("long.py:long_one")
        self.assertNotIn("TRUNCATED", whole)

    def test_outline_modes_still_work(self):
        self.assertTrue(self.slice("shop/models.py")[1].startswith("OUTLINE shop/models.py (47 lines)"))

    def test_unparsable_symbol_shows_raw_lines(self):
        code, out = self.slice("broken.py:Fine")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("RAW broken.py"))
        self.assertIn("showing raw lines", out)

    def test_errors(self):
        self.assertEqual(self.slice("../x.py:f")[0], 3)
        self.assertEqual(self.slice("nope.py:f")[0], 3)
        self.assertEqual(self.slice("shop/models.py", "--context", "-1")[0], 2)
        self.assertEqual(self.slice("shop/models.py:free", "--max-lines", "0")[0], 2)

    def test_deterministic(self):
        for target in ("shop/models.py:Cart", "shop/models.py:10-30", "shop/models.py"):
            self.assertEqual(self.slice(target), self.slice(target))


if __name__ == "__main__":
    unittest.main()
