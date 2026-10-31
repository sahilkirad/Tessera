from __future__ import annotations

import ast
import os
import sysconfig
import unittest
from pathlib import Path

import helpers  # noqa: F401  (puts scripts on sys.path)
from fixtures import FIXTURE
from helpers import make_repo, root_of

from _core import read_text
from _index import build_index, looks_newer, parse_file, render_outline


def def_names(node: ast.AST, prefix: str = "") -> list:
    """Independent qualname walker: classes, functions, methods; nothing inside functions."""
    out = []
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append(prefix + child.name)
        elif isinstance(child, ast.ClassDef):
            out.append(prefix + child.name)
            out += def_names(child, prefix + child.name + ".")
        elif not isinstance(child, ast.expr):
            out += def_names(child, prefix)
    return sorted(out)


def parse(text: str, path: str = "m.py"):
    warnings: list = []
    return parse_file(path, text, len(text), warnings), warnings


class ParsingTests(unittest.TestCase):
    def setUp(self):
        self.fi, self.warns = parse(FIXTURE["shop/models.py"], "shop/models.py")
        self.sym = {s.qualname: s for s in self.fi.symbols}

    def test_symbols_and_kinds(self):
        self.assertEqual(
            sorted(self.sym),
            ["Cart", "Cart.Meta", "Cart.Meta.Deep", "Cart.add", "Cart.sync", "Cart.tiny", "Cart.total",
             "Coupon", "documented", "free"])
        self.assertEqual(self.sym["Cart"].kind, "class")
        self.assertEqual(self.sym["Cart.add"].kind, "method")
        self.assertEqual(self.sym["free"].kind, "function")
        self.assertTrue(self.sym["Cart.sync"].is_async)
        self.assertNotIn("helper", " ".join(self.sym))

    def test_spans_include_decorators(self):
        cart, total = self.sym["Cart"], self.sym["Cart.total"]
        lines = FIXTURE["shop/models.py"].split("\n")
        self.assertEqual(lines[cart.start - 1], "@dataclass")
        self.assertEqual(lines[total.start - 1].strip(), "@property")
        self.assertEqual(total.decorators, ["@property"])
        self.assertTrue(lines[cart.end - 1].strip())

    def test_signatures_exact(self):
        self.assertEqual(self.sym["Cart.add"].signature, "def add(self, item, qty: int = 1) -> None")
        self.assertEqual(
            self.sym["Cart.sync"].signature,
            "async def sync(self,\n               remote: str,\n               *,\n               force: bool = False) -> bool")
        self.assertEqual(self.sym["Cart.tiny"].signature, "def tiny(self)")
        self.assertEqual(self.sym["free"].signature, "def free(x)")
        self.assertEqual(self.sym["Coupon"].signature, "class Coupon(Cart)")
        self.assertEqual(self.sym["Cart"].signature, "class Cart")

    def test_docs_params_fields_constants(self):
        self.assertEqual(self.sym["documented"].doc1, "Doc here.")
        self.assertEqual(self.sym["Cart.sync"].params, ["self", "remote", "force"])
        self.assertEqual(self.sym["Cart"].fields, ["items: list = None", "owner: str = ''"])
        self.assertEqual(self.sym["Cart.Meta.Deep"].fields, ["level: int = 3"])
        self.assertEqual(self.fi.module_doc1, "Shop models.")
        self.assertEqual(self.fi.constants[:2], ["MAX_ITEMS = 100", "DEFAULT_CURRENCY: str = 'USD'"])
        self.assertTrue(self.fi.constants[2].endswith("= ..."))
        self.assertTrue(all(len(c) <= 80 for c in self.fi.constants))
        self.assertEqual(len(self.fi.constants), 3)

    def test_broken_file_warns_and_falls_back(self):
        fi, warns = parse(FIXTURE["broken.py"], "broken.py")
        self.assertFalse(fi.parse_ok)
        self.assertEqual([s.name for s in fi.symbols], ["oops", "Fine"])
        self.assertEqual(len(warns), 1)
        self.assertTrue(warns[0].startswith("broken.py: could not parse"))

    def test_newer_syntax_classifier(self):
        src = "class Box[T]:\n    pass\n"
        self.assertTrue(looks_newer(src, (3, 11)))
        self.assertFalse(looks_newer(src, (3, 12)))
        self.assertTrue(looks_newer("match x:\n    case 1: pass\n", (3, 9)))
        self.assertTrue(looks_newer("try:\n    pass\nexcept* E:\n    pass\n", (3, 10)))
        self.assertFalse(looks_newer("def f(:\n", (3, 9)))

    def test_newer_syntax_file_on_this_python(self):
        fi, warns = parse(FIXTURE["newer.py"], "newer.py")
        if fi.parse_ok:
            self.assertEqual(warns, [])
        else:
            self.assertEqual(warns, ["newer.py: file uses syntax this Python cannot parse"])
            self.assertEqual([s.name for s in fi.symbols], ["Box"])

    def test_null_byte_and_empty(self):
        fi, warns = parse("x = 1\x00\n", "n.py")
        self.assertFalse(fi.parse_ok)
        self.assertEqual(len(warns), 1)
        empty, warns = parse("", "e.py")
        self.assertEqual((empty.loc, empty.symbols, warns), (0, [], []))

    def test_unicode_names(self):
        fi, _ = parse(FIXTURE["uni.py"], "uni.py")
        self.assertEqual([s.qualname for s in fi.symbols], ["gr\u00f6\u00dfe", "\u00dcn\u00ef", "\u00dcn\u00ef.m\u00e9thode"])

    def test_conditional_defs_are_symbols(self):
        fi, _ = parse("import sys\nif sys.platform:\n    def a(): pass\nelse:\n    def a(): pass\ntry:\n    class K: pass\nexcept Exception:\n    pass\n")
        self.assertEqual(sorted(s.qualname for s in fi.symbols), ["K", "a", "a"])


class RepoIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = make_repo(FIXTURE)
        cls.root = root_of(cls.tmp)
        cls.index = build_index(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def edges(self, path):
        return [(e.kind, e.target, e.module, e.names) for e in self.index.edges[path]]

    def test_module_map_roots_and_packages(self):
        mm = self.index.module_map
        self.assertEqual(mm["shop"], "shop/__init__.py")
        self.assertEqual(mm["shop.models"], "shop/models.py")
        self.assertEqual(mm["srclib.core"], "src/srclib/core.py")
        self.assertEqual(mm["xpkg.thing"], "packages/x/src/xpkg/thing.py")
        self.assertEqual(mm["ns.mod"], "ns/mod.py")
        self.assertNotIn("src.srclib.core", mm)

    def test_absolute_and_external(self):
        self.assertEqual(self.edges("app.py"), [
            ("internal", "src/srclib/core.py", "srclib.core", ["run"]),
            ("external", None, "requests", []),
        ])

    def test_relative_imports(self):
        self.assertEqual(self.edges("shop/billing.py"), [
            ("internal", "shop/models.py", "shop.models", ["Cart", "Coupon"]),
            ("internal", "shop/utils.py", "shop.utils", ["CouponValidator"]),
        ])

    def test_reexport_one_hop_and_submodule(self):
        got = self.edges("consumer.py")
        self.assertEqual(got[0], ("internal", "shop/models.py", "shop", ["Cart"]))
        self.assertEqual(got[1], ("internal", "shop/billing.py", "shop.billing", []))
        self.assertEqual(got[2][0], "unresolved")

    def test_nested_package_root_and_namespace(self):
        self.assertEqual(self.edges("use_x.py")[0][:2], ("internal", "packages/x/src/xpkg/thing.py"))
        self.assertEqual(self.edges("use_x.py")[1][:2], ("internal", "packages/x/src/xpkg/thing.py"))
        got = self.edges("ns/other.py")
        self.assertEqual(got[0][:2], ("internal", "ns/mod.py"))
        self.assertEqual(got[1][:2], ("internal", "ns/mod.py"))
        self.assertEqual(got[2][0], "unresolved")

    def test_circular_imports_recorded_both_ways(self):
        pairs = self.index.file_edges()
        self.assertIn(("shop/billing.py", "shop/utils.py"), pairs)
        self.assertIn(("shop/utils.py", "shop/billing.py"), pairs)

    def test_stdlib_is_external(self):
        self.assertEqual(self.edges("shop/utils.py")[1], ("external", None, "decimal", []))

    def test_broken_and_latin_files(self):
        self.assertFalse(self.index.files["broken.py"].parse_ok)
        self.assertTrue(self.index.files["latin.py"].parse_ok)
        self.assertTrue(any(w.startswith("broken.py: could not parse") for w in self.index.warnings))

    def test_module_name_clash_warns(self):
        with make_repo({"pkg.py": "", "pkg/__init__.py": ""}) as tmp:
            index = build_index(root_of(tmp))
            self.assertEqual(index.module_map["pkg"], "pkg.py")
            self.assertTrue(any("module name clash: pkg" in w for w in index.warnings))

    def test_deterministic(self):
        again = build_index(self.root)
        self.assertEqual(sorted(again.files), sorted(self.index.files))
        self.assertEqual(again.warnings, self.index.warnings)
        self.assertEqual(again.file_edges(), self.index.file_edges())


class OutlineTests(unittest.TestCase):
    def outline_body(self, text: str, path: str = "m.py") -> str:
        fi, _ = parse(text, path)
        self.assertTrue(fi.parse_ok)
        return render_outline(fi)

    def check_property(self, text: str, label: str):
        body = self.outline_body(text)
        self.assertEqual(def_names(ast.parse(body)), def_names(ast.parse(text)), label)

    def test_fixture_files_are_valid_and_complete(self):
        for rel, content in FIXTURE.items():
            if not isinstance(content, str):
                continue
            fi, _ = parse(content, rel)
            if not fi.parse_ok:
                continue
            with self.subTest(file=rel):
                self.check_property(content, rel)

    def test_outline_shape(self):
        body = self.outline_body(FIXTURE["shop/models.py"])
        lines = body.split("\n")
        self.assertEqual(lines[0], '"""Shop models."""')
        self.assertIn("MAX_ITEMS = 100", lines)
        self.assertIn("@dataclass", lines)
        self.assertIn('    """A shopping cart."""', lines)
        self.assertIn("    items: list = None", lines)
        self.assertIn("    def add(self, item, qty: int = 1) -> None: ...  # L21-23", lines)
        self.assertIn("    @property", lines)
        self.assertIn("class Coupon(Cart):", lines)
        self.assertIn("def documented(a: int) -> int:", lines)
        self.assertIn('    """Doc here."""  # L45-47', lines)
        self.assertIn("def free(x): ...  # L42-42", lines)
        self.assertNotIn("helper", body)

    def test_imports_hidden_unless_flag(self):
        fi, _ = parse("import os\nfrom . import x as y\nfrom a.b import c, d as e\n\n\ndef f(): pass\n")
        self.assertNotIn("import", render_outline(fi))
        shown = render_outline(fi, with_imports=True).split("\n")
        self.assertEqual(shown[:3], ["import os", "from . import x as y", "from a.b import c, d as e"])
        ast.parse(render_outline(fi, with_imports=True))

    def test_hostile_docstrings_stay_valid(self):
        src = 'def a():\n    \'\'\'He said "hi" \\\\ \'\'\'\n\n\nclass B:\n    """ends with quote\\""""\n'
        self.check_property(src, "docs")

    def test_stdlib_property(self):
        stdlib = Path(sysconfig.get_paths()["stdlib"])
        names = ["os.py", "argparse.py", "ast.py", "typing.py", "dataclasses.py", "textwrap.py",
                 "tokenize.py", "shutil.py", "asyncio/tasks.py", "collections/__init__.py", "enum.py"]
        checked = 0
        for name in names:
            path = stdlib / name
            if not path.is_file():
                continue
            text = read_text(path)
            fi, _ = parse(text, name)
            if not fi.parse_ok:
                continue
            with self.subTest(file=name):
                self.check_property(text, name)
                checked += 1
        self.assertGreater(checked, 3)

    def test_own_scripts_property(self):
        for path in sorted(helpers.SCRIPTS.glob("*.py")):
            with self.subTest(file=path.name):
                self.check_property(read_text(path), path.name)


if __name__ == "__main__":
    unittest.main()
