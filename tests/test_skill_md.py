"""SKILL.md rules from docs/SKILL_AND_PACKAGING.md, enforced."""
from __future__ import annotations

import re
import unittest

import helpers

SKILL_DIR = helpers.ROOT / "code-context-pruner"


def read_skill():
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    match = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
    assert match, "frontmatter missing"
    fields = dict(line.split(": ", 1) for line in match.group(1).split("\n"))
    return fields, match.group(2), text


class SkillMdTests(unittest.TestCase):
    def test_frontmatter_only_name_and_description(self):
        fields, _, _ = read_skill()
        self.assertEqual(sorted(fields), ["description", "name"])
        self.assertEqual(fields["name"], "code-context-pruner")
        self.assertRegex(fields["name"], r"^[a-z0-9-]+$")

    def test_description_is_task_based_and_short(self):
        fields, _, _ = read_skill()
        desc = fields["description"]
        self.assertLessEqual(len(desc), 1000)
        for phrase in ("fix a bug", "add a feature", "Python"):
            self.assertIn(phrase, desc)
        self.assertNotIn("save tokens", desc)

    def test_body_is_short_and_uses_skill_dir_paths(self):
        _, body, text = read_skill()
        self.assertLess(len(text.split("\n")), 150)
        self.assertIn("<skill_dir>/scripts/pack.py", body)
        self.assertNotRegex(body, r"python3? scripts/")
        self.assertIn("`python3`, or `python`, or `py` on Windows", body)

    def test_no_unmeasured_numbers_claimed(self):
        _, body, _ = read_skill()
        self.assertNotRegex(body, r"\d+\s*%")

    def test_referenced_files_exist(self):
        _, body, _ = read_skill()
        for script in set(re.findall(r"scripts/(\w+\.py)", body)):
            self.assertTrue((SKILL_DIR / "scripts" / script).is_file(), script)
        self.assertTrue((SKILL_DIR / "references" / "workflow.md").is_file())
        for name in ("README.md", "LICENSE"):
            self.assertTrue((SKILL_DIR / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
