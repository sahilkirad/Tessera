from __future__ import annotations

import io
import json
import random
import re
import unittest
from contextlib import redirect_stdout

import helpers
from helpers import make_repo, root_of

import deps as deps_cli
import pack as pack_cli
import _rank
from _core import estimate_tokens, printed_cost
from _index import build_index
from _index import parse_file
from _rank import Omission, _limited_line, _Source, deps_bfs, pack_context, seed_names

BILLING = '''"""Billing."""
from . import constants, helpers
from .base import BaseCalculator
from .models import Cart, Coupon
from .utils import CouponValidator


class PriceCalculator(BaseCalculator):
    """Handles pricing."""

    def fetch_subtotal(self):
        return 100.0

    def unrelated_method(self):
        return 0

    def inject_discounts(self, coupon_code: str) -> float:
        coupon = Coupon(coupon_code)
        valid = CouponValidator().validate(coupon_code)
        subtotal = self.fetch_subtotal()
        return helpers.round_money(subtotal) if valid else subtotal
'''
MODELS = "class Cart:\n" + "".join(
    "    def op%d(self, value):\n        total = value * %d\n        return total\n\n" % (i, i) for i in range(12)
) + "\n\nclass Coupon:\n    def __init__(self, code):\n        self.code = code\n"
SHOP = {
    "checkout/__init__.py": "",
    "checkout/billing.py": BILLING,
    "checkout/base.py": "class BaseCalculator:\n    def common(self):\n        return 1\n",
    "checkout/models.py": MODELS,
    "checkout/utils.py": "class CouponValidator:\n    def validate(self, code):\n        return True\n",
    "checkout/constants.py": "RATE = 0.2\n\n\ndef rate():\n    return RATE\n",
    "checkout/helpers.py": "def round_money(value):\n    return round(value, 2)\n\n\ndef other_func():\n    return 0\n",
    "notifications/email_service.py": "def send_receipt(order):\n    return order\n",
    "tests/test_billing.py": "def test_inject_discounts():\n    assert True\n",
}
BIG_METHODS = "".join(
    "    def m%d(self):\n%s        return %d\n\n" % (i, "".join("        x%d = %d\n" % (j, j) for j in range(28)), i)
    for i in range(20))
LIMITED = {
    "seed.py": "from big import BigThing\n\n\ndef widget_seed():\n    return BigThing()\n",
    "big.py": "class BigThing:\n" + BIG_METHODS,
}
GIANT = {"giant.py": "def giant_function_name():\n" + "".join("    value_%d = %d\n" % (i, i) for i in range(300)) + "    return 0\n"}


def run(module, argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = module.main(argv)
    return code, buf.getvalue()


def sections(result):
    return [(s.form, s.path, s.qualname) for s in result.sections]


class PackContentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = make_repo(SHOP)
        cls.index = build_index(root_of(cls.tmp))
        cls.result = pack_context(cls.index, "inject discounts", 4000, "explicit")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_header_and_seed(self):
        self.assertTrue(self.result.text.startswith(
            'PACK "inject discounts" confidence=HIGH budget=4000 (explicit) seeds: PriceCalculator.inject_discounts\n'))
        self.assertIn(("FULL", "checkout/billing.py", "PriceCalculator.inject_discounts"), sections(self.result))

    def test_referenced_class_is_full_for_that_class_only(self):
        found = sections(self.result)
        self.assertIn(("FULL", "checkout/models.py", "Coupon"), found)
        self.assertIn(("FULL", "checkout/utils.py", "CouponValidator"), found)
        self.assertNotIn(("FULL", "checkout/models.py", "Cart"), found)
        self.assertNotIn("def op0", self.result.text.split("=== OUTLINE checkout/models.py")[0])

    def test_seed_context_siblings_bases_and_module_calls(self):
        found = sections(self.result)
        self.assertIn(("FULL", "checkout/billing.py", "PriceCalculator.fetch_subtotal"), found)
        self.assertNotIn(("FULL", "checkout/billing.py", "PriceCalculator.unrelated_method"), found)
        self.assertIn(("FULL", "checkout/base.py", "BaseCalculator"), found)
        self.assertIn(("FULL", "checkout/helpers.py", "round_money"), found)
        self.assertNotIn(("FULL", "checkout/helpers.py", "other_func"), found)

    def test_neighbours_are_outlines_and_sections_are_sorted(self):
        forms = {(s.form, s.path) for s in self.result.sections}
        self.assertIn(("OUTLINE", "checkout/constants.py"), forms)
        self.assertNotIn(("OUTLINE", "checkout/models.py"), forms)
        keys = [(s.path, s.start) for s in self.result.sections]
        self.assertEqual(keys, sorted(keys))
        headings = [l for l in self.result.text.split("\n") if l.startswith("=== ")]
        self.assertEqual(len(headings), len(self.result.sections))

    def test_footer_tokens_line_and_savings(self):
        match = re.search(r"TOKENS: ~(\d+) / 4000 \(estimate\)\. Whole contributing files ~(\d+), saved ~(\d+)% \(estimate\)",
                          self.result.text)
        self.assertIsNotNone(match)
        used, baseline, saved = (int(g) for g in match.groups())
        self.assertEqual(used, self.result.tokens_used)
        self.assertEqual(baseline, self.result.baseline_tokens)
        self.assertEqual(saved, max(0, round((1 - used / baseline) * 100)))

    def test_nothing_relevant_omitted_means_no_budget_limited(self):
        self.assertFalse(self.result.budget_limited)
        self.assertNotIn("BUDGET-LIMITED", self.result.text)
        self.assertIsNone(self.result.suggested_budget)

    def test_deterministic(self):
        again = pack_context(self.index, "inject discounts", 4000, "explicit")
        self.assertEqual(again.text, self.result.text)

    def test_test_files_only_seed_for_task_test(self):
        plain = pack_context(self.index, "test inject discounts", 2000, "default")
        with_tests = pack_context(self.index, "test inject discounts", 2000, "task", "test")
        self.assertNotEqual(plain.seeds[:1], ["test_inject_discounts"])
        self.assertEqual(with_tests.seeds[0], "test_inject_discounts")


class SeedNamesTests(unittest.TestCase):
    def test_names_self_calls_and_attribute_calls(self):
        text = ("import os\n\n\nclass A:\n    def m(self):\n        self.helper()\n"
                "        os.path.join('a')\n        return mod.run(zzz)\n")
        with make_repo({"a.py": text}) as tmp:
            index = build_index(root_of(tmp))
            sym = next(s for s in index.files["a.py"].symbols if s.qualname == "A.m")
            names, own, attrs = seed_names(_Source(index), sym)
        self.assertTrue({"os", "mod", "zzz"} <= names)
        self.assertEqual(own, {"helper"})
        self.assertEqual(attrs, {("mod", "run")})

    def test_self_attribute_references_count_as_siblings(self):
        text = ("class A:\n    def compute_total(self):\n        return wrap(self._inner)\n\n"
                "    def _inner(self):\n        return 1\n")
        with make_repo({"a.py": text}) as tmp:
            index = build_index(root_of(tmp))
            sym = next(s for s in index.files["a.py"].symbols if s.qualname == "A.compute_total")
            _, own, _ = seed_names(_Source(index), sym)
            result = pack_context(index, "compute total", 2000)
        self.assertEqual(own, {"_inner"})
        self.assertIn("A._inner", {s.qualname for s in result.sections if s.form == "FULL"})


class PackBudgetTests(unittest.TestCase):
    def check_budgets(self, root, queries, rng):
        index = build_index(root)
        budgets = [rng.randint(300, 8000) for _ in range(50)] + [300, 8000]
        for budget in budgets:
            query = rng.choice(queries)
            result = pack_context(index, query, budget, "explicit")
            self.assertLessEqual(printed_cost(result.text), budget, (budget, query))
            self.assertEqual(result.tokens_used, estimate_tokens(result.text), (budget, query))

    def test_property_never_exceeds_budget_on_fixture(self):
        files = dict(SHOP, **LIMITED, **GIANT)
        for i in range(25):
            files["extra/mod%d.py" % i] = "from checkout.helpers import round_money\n\n\ndef extra_%d(v):\n    return round_money(v)\n" % i
        with make_repo(files) as tmp:
            self.check_budgets(root_of(tmp), ["inject discounts", "widget seed", "giant function name", "extra", "round money"],
                               random.Random(11))

    def test_property_never_exceeds_budget_on_own_scripts(self):
        self.check_budgets(str(helpers.SCRIPTS), ["pagerank rank files", "estimate tokens", "build index",
                                                  "slice report outline", "pack context seeds"], random.Random(5))

    def test_budget_above_cap_is_clamped_with_warning(self):
        with make_repo(SHOP) as tmp:
            for requested in ("8001", "9000", "1000000"):
                code, out = run(pack_cli, ["inject discounts", "--root", root_of(tmp), "--budget", requested])
                self.assertEqual(code, 0)
                self.assertIn("budget=8000 (clamped)", out)
                self.assertIn("budget %s clamped to 8000" % requested, out)
                self.assertLessEqual(printed_cost(out[:-1]), 8000)

    def test_below_minimum_and_usage_errors(self):
        with make_repo(SHOP) as tmp:
            root = root_of(tmp)
            self.assertEqual(run(pack_cli, ["x", "--root", root, "--budget", "199"]), (0, "BUDGET TOO SMALL (minimum 200)\n"))
            self.assertEqual(run(pack_cli, ["x", "--root", root, "--task", "huge"])[0], 2)
            self.assertEqual(run(pack_cli, ["x", "--root", root, "--budget", "0"])[0], 2)
            self.assertEqual(run(pack_cli, ["x", "--root", root, "--seeds", "0"])[0], 2)
            self.assertEqual(run(pack_cli, ["x", "--root", root + "/nope"])[0], 3)

    def test_task_profiles_resolve(self):
        with make_repo(SHOP) as tmp:
            root = root_of(tmp)
            for task, budget in (("lookup", 1500), ("test", 2000), ("bug", 2500), ("explore", 3000), ("feature", 3500)):
                data = json.loads(run(pack_cli, ["inject discounts", "--root", root, "--task", task, "--json"])[1])
                self.assertEqual((data["task"], data["budget"], data["budget_source"]), (task, budget, "task"))
            data = json.loads(run(pack_cli, ["inject discounts", "--root", root, "--json"])[1])
            self.assertEqual((data["task"], data["budget"], data["budget_source"]), (None, 2000, "default"))
            data = json.loads(run(pack_cli, ["inject discounts", "--root", root, "--budget", "700", "--task", "bug", "--json"])[1])
            self.assertEqual((data["budget"], data["budget_source"]), (700, "explicit"))

    def test_warnings_are_capped_and_budget_holds(self):
        files = dict(SHOP, **{"bad%03d.py" % i: "def broken(:\n" for i in range(200)})
        with make_repo(files) as tmp:
            code, out = run(pack_cli, ["inject discounts", "--root", root_of(tmp), "--budget", "600"])
        warn = [l for l in out.split("\n") if l.startswith("WARNINGS:")]
        self.assertEqual(code, 0)
        self.assertEqual(len(warn), 1)
        self.assertLessEqual(warn[0].count("could not parse"), 5)
        self.assertIn(" more", warn[0])
        self.assertLessEqual(printed_cost(out[:-1]), 600)


class PackTruncationAndLimitTests(unittest.TestCase):
    def test_top_seed_bigger_than_budget_is_truncated_never_overflows(self):
        with make_repo(GIANT) as tmp:
            for budget in (200, 300, 500, 1000):
                code, out = run(pack_cli, ["giant function name", "--root", root_of(tmp), "--budget", str(budget)])
                self.assertEqual(code, 0)
                self.assertLessEqual(printed_cost(out[:-1]), budget)
                if "=== TRUNCATED" in out:
                    self.assertRegex(out, r"TRUNCATED \(lines 1-\d+ of 1-302\): use slice giant\.py:\d+-302")
                    self.assertIn("def giant_function_name():", out)
            _, out = run(pack_cli, ["giant function name", "--root", root_of(tmp), "--budget", "500"])
            self.assertIn("=== TRUNCATED giant.py::giant_function_name L1-", out)
            self.assertIn("BUDGET-LIMITED", out)

    def test_budget_limited_when_referenced_class_downgraded(self):
        with make_repo(LIMITED) as tmp:
            root = root_of(tmp)
            code, out = run(pack_cli, ["widget seed", "--root", root, "--budget", "2000"])
            data = json.loads(run(pack_cli, ["widget seed", "--root", root, "--budget", "2000", "--json"])[1])
        self.assertEqual(code, 0)
        self.assertTrue(data["budget_limited"])
        self.assertEqual(data["suggested_budget"], 2500)
        self.assertIn("BUDGET-LIMITED: 1 relevant items omitted (big.py::BigThing). Rerun with --task bug or --budget 2500, or use slice.py.", out)
        self.assertIn("=== OUTLINE big.py::BigThing", out)
        self.assertIn("big.py::BigThing (outline only)", out)

    def test_budget_limited_when_referenced_class_omitted(self):
        with make_repo(LIMITED) as tmp:
            root = root_of(tmp)
            _, out = run(pack_cli, ["widget seed", "--root", root, "--budget", "1000"])
            data = json.loads(run(pack_cli, ["widget seed", "--root", root, "--budget", "1000", "--json"])[1])
        self.assertTrue(data["budget_limited"])
        self.assertEqual(data["suggested_budget"], 1500)
        self.assertIn("OMITTED: big.py::BigThing", out)
        self.assertIn("Rerun with --task lookup or --budget 1500, or use slice.py.", out)

    def test_no_budget_limited_when_everything_fits(self):
        with make_repo(LIMITED) as tmp:
            _, out = run(pack_cli, ["widget seed", "--root", root_of(tmp), "--budget", "8000"])
        self.assertIn("=== FULL big.py::BigThing", out)
        self.assertNotIn("BUDGET-LIMITED", out)

    def test_hard_cap_message(self):
        line = _limited_line([Omission("a.py::X", "a.py::X", 0.8)], 8000)
        self.assertEqual(line, "BUDGET-LIMITED: 1 relevant items omitted (a.py::X). At the hard cap; use slice.py.")
        self.assertIn("--budget 7500", _limited_line([Omission("a.py::X", "a.py::X", 0.8)], 5000))

    def test_low_confidence_gives_candidates_and_vocabulary_no_code(self):
        with make_repo(SHOP) as tmp:
            code, out = run(pack_cli, ["zzzz qqqq", "--root", root_of(tmp), "--budget", "400"])
        self.assertEqual(code, 0)
        self.assertIn("confidence=LOW", out)
        self.assertIn("Candidates (no code):", out)
        self.assertIn("Repo vocabulary:", out)
        self.assertIn("Retry with 3-6 identifier-like words", out)
        self.assertNotIn("=== ", out)
        self.assertLessEqual(printed_cost(out[:-1]), 400)

    def test_json_shape(self):
        with make_repo(SHOP) as tmp:
            data = json.loads(run(pack_cli, ["inject discounts", "--root", root_of(tmp), "--json"])[1])
        self.assertEqual(set(data), {"confidence", "task", "budget_source", "sections", "omitted", "warnings",
                                     "tokens_used", "budget", "budget_limited", "suggested_budget",
                                     "baseline_tokens", "candidates", "vocabulary"})
        self.assertEqual(set(data["sections"][0]), {"form", "path", "qualname", "start", "end", "tokens"})

    def test_no_python_files(self):
        with make_repo({"a.txt": "x"}) as tmp:
            code, out = run(pack_cli, ["x", "--root", root_of(tmp)])
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("NO PYTHON FILES"))


CHAIN = {"a.py": "import b\n", "b.py": "import c\n", "c.py": "import d\n", "d.py": "import e\n", "e.py": "import f\nimport requests\n",
         "f.py": "x = 1\n"}
CYCLE = {"p.py": "from q import y\nimport requests\nimport json\nfrom . import nothing_here\n", "q.py": "from p import x\n\ny = 1\n",
         "r.py": "import p\n", "s.py": "from p import x\n"}


class DepsTests(unittest.TestCase):
    def test_cycle_terminates_and_marks_already_shown(self):
        with make_repo(CYCLE) as tmp:
            code, out = run(deps_cli, ["p.py", "--root", root_of(tmp)])
        self.assertEqual(code, 0)
        lines = out.split("\n")
        self.assertEqual(lines[0], "DEPS p.py depth=2")
        self.assertEqual(lines[1], "L1  q.py  (y)  w=1.0")
        self.assertEqual(lines[2], "  L2  p.py  (already shown)")
        self.assertIn("EXTERNAL/UNRESOLVED: json, requests, . (unresolved)", out)

    def test_depth_capped_at_three(self):
        with make_repo(CHAIN) as tmp:
            root = root_of(tmp)
            _, out3 = run(deps_cli, ["a.py", "--root", root, "--depth", "3"])
            _, out9 = run(deps_cli, ["a.py", "--root", root, "--depth", "9"])
            _, out1 = run(deps_cli, ["a.py", "--root", root, "--depth", "1"])
        self.assertIn("    L3  d.py  (module)  w=0.3", out3)
        self.assertNotIn("e.py", out3.split("OMITTED")[0])
        self.assertIn("1 files beyond depth 3", out3)
        self.assertIn("depth 9 clamped to 3", out9)
        self.assertNotIn("L4", out9)
        self.assertIn("1 files beyond depth 1 (use --depth 2)", out1)

    def test_bfs_levels_and_weights(self):
        with make_repo(CHAIN) as tmp:
            result = deps_bfs(build_index(root_of(tmp)), "a.py", 3)
        self.assertEqual(result.levels, {"a.py": 0, "b.py": 1, "c.py": 2, "d.py": 3})
        self.assertEqual(result.external, [])

    def test_reverse(self):
        with make_repo(CYCLE) as tmp:
            code, out = run(deps_cli, ["p.py", "--reverse", "--root", root_of(tmp)])
        self.assertEqual(code, 0)
        self.assertEqual(out.split("\n")[:4], ["IMPORTED-BY p.py (3 files)", "q.py", "r.py", "s.py"])

    def test_errors(self):
        with make_repo(CYCLE) as tmp:
            root = root_of(tmp)
            self.assertEqual(run(deps_cli, ["../x.py", "--root", root])[0], 3)
            self.assertEqual(run(deps_cli, ["nope.py", "--root", root])[0], 3)
            self.assertEqual(run(deps_cli, ["p.py", "--root", root, "--depth", "0"])[0], 2)

    def test_deterministic(self):
        with make_repo(CYCLE) as tmp:
            args = ["p.py", "--root", root_of(tmp)]
            self.assertEqual(run(deps_cli, args), run(deps_cli, args))


def crowded_repo():
    files = {
        "pkg/__init__.py": "",
        "pkg/util.py": "def shared_helper():\n    return 1\n\n\ndef rare_helper():\n    return 2\n",
        "pkg/core.py": ("from pkg.util import rare_helper, shared_helper\n\n\n"
                        "def compute_report():\n    return shared_helper() + rare_helper()\n"),
    }
    for i in range(10):
        files["pkg/user%d.py" % i] = "from pkg.util import shared_helper\n\n\ndef use%d():\n    return shared_helper()\n" % i
    return files


class UbiquitousHelperTests(unittest.TestCase):
    def priorities(self, query):
        from _rank import pack_context as pack
        with make_repo(crowded_repo()) as tmp:
            result = pack(build_index(root_of(tmp)), query, 2000)
        return {s.qualname: s.priority for s in result.sections if s.form == "FULL"}

    def test_helper_imported_by_many_files_is_demoted(self):
        prios = self.priorities("compute report")
        self.assertEqual(prios["rare_helper"], _rank.PRIORITY_REF)
        self.assertEqual(prios["shared_helper"], _rank.PRIORITY_UBIQUITOUS)

    def test_query_naming_the_helper_keeps_it_referenced(self):
        prios = self.priorities("compute report shared helper")
        self.assertGreaterEqual(prios["shared_helper"], _rank.PRIORITY_REF)


class TestModeDemotionTests(unittest.TestCase):
    FILES = {
        "tests/test_zone.py": "def test_zone_rate():\n    assert True\n",
        "zcode/zone.py": "def zone_rate():\n    return 1\n",
    }

    def first_hit(self, **kwargs):
        with make_repo(self.FILES) as tmp:
            hits = _rank.rank_symbols(build_index(root_of(tmp)), ["zone", "rate"], **kwargs).hits
        return hits[0].symbol.path

    def test_default_demotes_tests(self):
        self.assertEqual(self.first_hit(), "zcode/zone.py")

    def test_test_mode_without_factor_does_not_demote(self):
        self.assertEqual(self.first_hit(include_tests=True), "tests/test_zone.py")

    def test_test_mode_profile_demotes_partially(self):
        self.assertTrue(_rank.TEST_DEMOTION < _rank.TEST_MODE_DEMOTION < 1.0)
        self.assertEqual(self.first_hit(include_tests=True, test_factor=_rank.TEST_MODE_DEMOTION),
                         "zcode/zone.py")


if __name__ == "__main__":
    unittest.main()
