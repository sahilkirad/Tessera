from __future__ import annotations

import io
import json
import re
import unittest
from contextlib import redirect_stdout

import helpers  # noqa: F401
from helpers import make_repo, root_of

import find as find_cli
from _index import build_index
from _rank import rank_symbols, tokenize

WORDS = ("alder birch cedar dogwood elm fir ginkgo hazel iris juniper kauri larch maple nutmeg "
         "olive poplar quince rowan spruce tamarack umbrella vine willow yew acacia banyan cypress "
         "dahlia elder fennel gorse holly ivy jasmine kale linden mimosa nettle oak pine").split()


def base_files():
    files = {
        "billing.py": (
            "class PriceCalculator:\n"
            "    def apply_discount(self, coupon_code: str) -> float:\n"
            "        return 1.0\n\n"
            "    def calculate_tax(self) -> float:\n"
            "        return 0.18\n"
        ),
        "checkout/coupons.py": (
            "class CouponValidator:\n"
            "    def validate(self, code: str) -> bool:\n"
            '        """Check a promo code."""\n'
            "        return True\n"
        ),
        "bonus.py": "def applyBonus(points):\n    return points\n",
        "docs_only.py": 'def process(cart):\n    """Apply discount to the cart totals."""\n    return cart\n',
        "zoo.py": "def zebra_crossing():\n    pass\n" + "".join(
            "\n\ndef tiger_%s():\n    pass\n" % c for c in "abcd"),
        "rhino.py": "".join("def rhino_%s():\n    pass\n\n\n" % c for c in "abcdefghijkl"),
        "aaa_tests/test_billing.py": "def test_apply_discount():\n    pass\n",
    }
    for word in WORDS:
        files["noise/%s.py" % word] = "def get_%s(self, data):\n    return data\n" % word
    return files


def run(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = find_cli.main(argv)
    return code, buf.getvalue()


class TokenizeTests(unittest.TestCase):
    def test_splitting(self):
        self.assertEqual(tokenize("applyDiscount"), ["apply", "discount"])
        self.assertEqual(tokenize("apply_discount"), ["apply", "discount"])
        self.assertEqual(tokenize("HTTPServer sha256 x"), ["http", "server", "sha", "256"])
        self.assertEqual(tokenize("where is the Cart?"), ["cart"])
        self.assertEqual(tokenize("größe Café"), ["größe", "café"])
        self.assertEqual(tokenize(""), [])


class RankingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = make_repo(base_files())
        cls.index = build_index(root_of(cls.tmp))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def rank(self, query, **kw):
        return rank_symbols(self.index, tokenize(query), **kw)

    def top_names(self, result, n=3):
        return [h.symbol.qualname for h in result.hits[:n]]

    def test_camel_and_snake_both_ways(self):
        self.assertEqual(self.top_names(self.rank("applyDiscount"), 1), ["PriceCalculator.apply_discount"])
        self.assertEqual(self.top_names(self.rank("apply_bonus"), 1), ["applyBonus"])

    def test_rare_terms_outrank_common(self):
        result = self.rank("get zebra")
        self.assertEqual(result.hits[0].symbol.qualname, "zebra_crossing")

    def test_name_match_outranks_docstring_match(self):
        result = self.rank("apply discount", include_tests=False)
        names = self.top_names(result, 4)
        self.assertEqual(names[0], "PriceCalculator.apply_discount")
        self.assertLess(names.index("PriceCalculator.apply_discount"), names.index("process"))

    def test_test_files_demoted_unless_included(self):
        demoted = self.rank("apply discount")
        included = self.rank("apply discount", include_tests=True)
        self.assertEqual(demoted.hits[0].symbol.qualname, "PriceCalculator.apply_discount")
        self.assertEqual(included.hits[0].symbol.qualname, "test_apply_discount")
        score = {h.symbol.qualname: h.score for h in included.hits}
        self.assertAlmostEqual(score["test_apply_discount"], score["PriceCalculator.apply_discount"], places=9)

    def test_prefix_match_needs_four_chars(self):
        self.assertEqual(self.top_names(self.rank("zebr"), 1), ["zebra_crossing"])
        self.assertEqual(self.rank("zeb").hits, [])

    def test_docstring_and_param_fields_match(self):
        self.assertIn("CouponValidator.validate", self.top_names(self.rank("promo"), 1))
        self.assertEqual(self.top_names(self.rank("points"), 1), ["applyBonus"])

    def test_confidence_levels(self):
        self.assertEqual(self.rank("apply discount").confidence, "HIGH")
        self.assertEqual(self.rank("zebra").confidence, "HIGH")
        self.assertEqual(self.rank("tiger").confidence, "MEDIUM")
        self.assertEqual(self.rank("get").confidence, "LOW")
        self.assertEqual(self.rank("nonexistent words").confidence, "LOW")

    def test_matched_and_unmatched_reported(self):
        result = self.rank("discount coupon promo nothingmatches")
        self.assertIn("nothingmatches", result.unmatched)
        self.assertEqual(result.unmatched, ["nothingmatches"])
        self.assertEqual(result.matched, ["discount", "coupon", "promo"])
        self.assertEqual(sorted(result.matched + result.unmatched), sorted(result.terms))

    def test_low_gives_vocabulary_and_never_raises(self):
        result = self.rank("qqqq zzzz")
        self.assertEqual((result.confidence, result.hits), ("LOW", []))
        self.assertTrue(0 < len(result.vocabulary) <= 30)
        self.assertNotIn("get", result.vocabulary)
        for empty in ("", "the of"):
            self.assertEqual(self.rank(empty).confidence, "LOW")

    def test_scores_bounded_and_deterministic(self):
        first = self.rank("get data apply discount")
        second = self.rank("get data apply discount")
        self.assertTrue(all(0.0 <= h.score <= 1.0 for h in first.hits))
        self.assertEqual([(h.symbol.qualname, h.score) for h in first.hits],
                         [(h.symbol.qualname, h.score) for h in second.hits])

    def test_empty_repo(self):
        with make_repo({"a.txt": "x"}) as tmp:
            result = rank_symbols(build_index(root_of(tmp)), ["anything"])
        self.assertEqual((result.confidence, result.hits, result.vocabulary), ("LOW", [], []))


class FindCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = make_repo(base_files())
        cls.root = root_of(cls.tmp)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_high_output_format(self):
        code, out = run(["apply discount nothingmatches", "--root", self.root])
        self.assertEqual(code, 0)
        lines = out.split("\n")
        self.assertEqual(lines[0], 'FIND "apply discount nothingmatches" confidence=HIGH matched=2/3 terms (unmatched: nothingmatches)')
        self.assertRegex(lines[1], r"^1  \d\.\d\d  billing\.py::PriceCalculator\.apply_discount  L2-3$")
        self.assertEqual(lines[2], "        def apply_discount(self, coupon_code: str) -> float")

    def test_omitted_footer_suggests_top(self):
        _, out = run(["rhino", "--root", self.root])
        self.assertIn("confidence=MEDIUM", out)
        self.assertIn("OMITTED: 4 lower-scoring matches (use --top 20)", out)
        _, out = run(["rhino", "--root", self.root, "--top", "100"])
        self.assertNotIn("OMITTED:", out)

    def test_low_output(self):
        code, out = run(["qqqq zzzz", "--root", self.root])
        self.assertEqual(code, 0)
        lines = out.split("\n")
        self.assertEqual(lines[0], 'FIND "qqqq zzzz" confidence=LOW')
        self.assertTrue(lines[1].startswith("No strong match. Repo vocabulary: "))
        self.assertIn("Retry with 3-6 identifier-like words", lines[2])
        self.assertIn("`map.py <folder>`", lines[2])

    def test_json(self):
        code, out = run(["zebra", "--root", self.root, "--json"])
        data = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(data["confidence"], "HIGH")
        first = data["results"][0]
        self.assertEqual((first["rank"], first["path"], first["qualname"]), (1, "zoo.py", "zebra_crossing"))
        self.assertEqual(set(first), {"rank", "score", "path", "qualname", "start", "end", "signature"})
        self.assertEqual(data["vocabulary"], [])
        low = json.loads(run(["qqqq", "--root", self.root, "--json"])[1])
        self.assertEqual((low["confidence"], low["results"]), ("LOW", []))
        self.assertTrue(low["vocabulary"])

    def test_errors_and_edge_inputs(self):
        self.assertEqual(run(["x", "--root", self.root, "--top", "0"])[0], 2)
        self.assertEqual(run(["--root", self.root])[0], 2)
        self.assertEqual(run(["x", "--root", self.root + "/missing"])[0], 3)
        code, out = run(["", "--root", self.root])
        self.assertEqual(code, 0)
        self.assertIn("confidence=LOW", out)

    def test_no_python_files(self):
        with make_repo({"a.txt": "x"}) as tmp:
            code, out = run(["x", "--root", root_of(tmp)])
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("NO PYTHON FILES"))

    def test_deterministic(self):
        args = ["apply discount", "--root", self.root]
        self.assertEqual(run(args), run(args))


if __name__ == "__main__":
    unittest.main()
