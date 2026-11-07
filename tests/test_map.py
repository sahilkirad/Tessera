from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout

import helpers  # noqa: F401
from fixtures import FIXTURE
from helpers import make_repo, root_of

import map as map_cli
import slice as slice_cli
from _core import printed_cost
from _index import build_index
from _rank import file_ranks, pagerank


def run(module, argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = module.main(argv)
    return code, buf.getvalue()


def hub_repo(n: int = 40):
    files = {"hub.py": "def shared():\n    return 1\n", "lonely.py": "def alone():\n    return 2\n"}
    for i in range(n):
        body = "from hub import shared\n\n\nclass Thing%d:\n    def go(self):\n        return shared()\n" % i
        files["pkg/mod%02d.py" % i] = body
    return files


class PageRankTests(unittest.TestCase):
    def test_chain_and_sum(self):
        ranks = pagerank(["a", "b", "c"], [("a", "b"), ("b", "c")])
        self.assertGreater(ranks["c"], ranks["b"])
        self.assertGreater(ranks["b"], ranks["a"])
        self.assertAlmostEqual(sum(ranks.values()), 1.0, places=9)

    def test_cycle_terminates_and_empty(self):
        ranks = pagerank(["a", "b"], [("a", "b"), ("b", "a")])
        self.assertAlmostEqual(ranks["a"], ranks["b"], places=9)
        self.assertEqual(pagerank([], []), {})

    def test_unknown_and_self_edges_ignored(self):
        ranks = pagerank(["a"], [("a", "a"), ("a", "zzz")])
        self.assertAlmostEqual(ranks["a"], 1.0, places=9)

    def test_imported_file_outranks_unimported(self):
        with make_repo(hub_repo(10)) as tmp:
            ranks = file_ranks(build_index(root_of(tmp)))
        self.assertGreater(ranks["hub.py"], ranks["lonely.py"])


class MapTests(unittest.TestCase):
    def test_hub_listed_before_lonely_with_counts(self):
        with make_repo(hub_repo(40)) as tmp:
            code, out = run(map_cli, ["--root", root_of(tmp), "--budget", "4000"])
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("MAP root="))
        self.assertLess(out.index("hub.py"), out.index("lonely.py"))
        self.assertIn("hub.py  imported_by=40 loc=2", out)
        self.assertIn("  def shared", out)
        self.assertIn("class Thing0: go", out)

    def test_never_exceeds_budget(self):
        with make_repo(hub_repo(60)) as tmp:
            root = root_of(tmp)
            for budget in (200, 201, 250, 300, 400, 500, 750, 1000, 1500, 2000, 3000):
                code, out = run(map_cli, ["--root", root, "--budget", str(budget)])
                self.assertEqual(code, 0)
                self.assertLessEqual(printed_cost(out[:-1]), budget, (budget, out[:200]))
                self.assertIn("MAP root=", out)

    def test_omitted_footer_when_cut(self):
        with make_repo(hub_repo(60)) as tmp:
            _, out = run(map_cli, ["--root", root_of(tmp), "--budget", "300"])
        self.assertIn("OMITTED:", out)
        self.assertIn("narrow with `map.py <folder>`", out)
        self.assertIn("pkg/", out)

    def test_budget_too_small_and_default(self):
        with make_repo(hub_repo(3)) as tmp:
            root = root_of(tmp)
            self.assertEqual(run(map_cli, ["--root", root, "--budget", "199"]), (0, "BUDGET TOO SMALL (minimum 200)\n"))
            code, out = run(map_cli, ["--root", root])
            self.assertEqual(code, 0)
            self.assertIn("shown=5", out)

    def test_budget_above_cap_is_clamped_with_warning(self):
        with make_repo(hub_repo(3)) as tmp:
            _, out = run(map_cli, ["--root", root_of(tmp), "--budget", "99999"])
        self.assertIn("clamped to 8000", out)

    def test_usage_and_path_errors(self):
        with make_repo(hub_repo(2)) as tmp:
            root = root_of(tmp)
            self.assertEqual(run(map_cli, ["--root", root, "--budget", "0"])[0], 2)
            self.assertEqual(run(map_cli, ["--root", root, "--budget", "abc"])[0], 2)
            code, out = run(map_cli, ["--root", root, "../elsewhere"])
            self.assertEqual(code, 3)
            self.assertTrue(out.startswith("ERROR:"))
            self.assertEqual(run(map_cli, ["--root", root + "/nope"])[0], 3)
            self.assertEqual(run(map_cli, ["--root", root, "hub.py"])[0], 3)

    def test_focus_folder(self):
        with make_repo(FIXTURE) as tmp:
            code, out = run(map_cli, ["shop", "--root", root_of(tmp), "--budget", "2000"])
        self.assertEqual(code, 0)
        self.assertIn("focus=shop/", out)
        self.assertIn("shop/models.py", out)
        self.assertNotIn("app.py", out)

    def test_fixture_warnings_and_unicode(self):
        with make_repo(FIXTURE) as tmp:
            code, out = run(map_cli, ["--root", root_of(tmp), "--budget", "3000"])
        self.assertEqual(code, 0)
        self.assertIn("broken.py: could not parse", out)
        self.assertIn("def gr\u00f6\u00dfe", out)
        self.assertIn("class \u00dcn\u00ef: m\u00e9thode", out)
        self.assertNotIn("requests", out)

    def test_deterministic(self):
        with make_repo(FIXTURE) as tmp:
            first = run(map_cli, ["--root", root_of(tmp), "--budget", "1200"])
            second = run(map_cli, ["--root", root_of(tmp), "--budget", "1200"])
        self.assertEqual(first, second)

    def test_name_limit_per_file(self):
        body = "\n".join("def f%d(): pass" % i for i in range(12)) + "\n"
        with make_repo({"many.py": body}) as tmp:
            _, out = run(map_cli, ["--root", root_of(tmp)])
        self.assertIn("  def f0, f1, f2, f3, f4, f5, f6, f7", out)
        self.assertIn("(+4 more)", out)

    def test_no_python_files(self):
        with make_repo({"readme.txt": "hi"}) as tmp:
            code, out = run(map_cli, ["--root", root_of(tmp)])
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("NO PYTHON FILES: tessera v1 supports Python only"))

    def test_partial_on_expired_deadline(self):
        with make_repo(hub_repo(5)) as tmp:
            code, out = run(map_cli, ["--root", root_of(tmp), "--max-seconds", "0"])
        self.assertEqual(code, 0)
        self.assertTrue("PARTIAL" in out or "NO PYTHON FILES" in out)


class SliceOutlineTests(unittest.TestCase):
    def test_outline_cli(self):
        with make_repo(FIXTURE) as tmp:
            code, out = run(slice_cli, ["shop/models.py", "--root", root_of(tmp)])
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("OUTLINE shop/models.py (47 lines)\n"))
        self.assertIn("class Cart:", out)

    def test_imports_flag(self):
        with make_repo(FIXTURE) as tmp:
            _, out = run(slice_cli, ["shop/billing.py", "--root", root_of(tmp), "--imports"])
        self.assertIn("from .models import Cart, Coupon", out)

    def test_unparsable_shows_raw_lines(self):
        with make_repo(FIXTURE) as tmp:
            code, out = run(slice_cli, ["broken.py", "--root", root_of(tmp)])
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("RAW broken.py (first 5 of 5 lines)\n"))
        self.assertIn("def oops(:", out)
        self.assertIn("WARNINGS: broken.py: could not parse", out)
        self.assertTrue(out.rstrip().endswith("showing raw lines"))

    def test_errors(self):
        with make_repo(FIXTURE) as tmp:
            root = root_of(tmp)
            self.assertEqual(run(slice_cli, ["../x.py", "--root", root])[0], 3)
            self.assertEqual(run(slice_cli, ["shop", "--root", root])[0], 2)
            self.assertEqual(run(slice_cli, ["--root", root])[0], 2)

    def test_deterministic(self):
        with make_repo(FIXTURE) as tmp:
            args = ["shop/models.py", "--root", root_of(tmp)]
            self.assertEqual(run(slice_cli, args), run(slice_cli, args))


if __name__ == "__main__":
    unittest.main()
