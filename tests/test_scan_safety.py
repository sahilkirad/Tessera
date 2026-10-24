"""Static scan of shipped scripts for patterns Agensi's security scan flags."""
from __future__ import annotations

import ast
import unittest

import helpers

BANNED_MODULES = {
    "socket", "urllib", "http", "ftplib", "smtplib", "requests", "subprocess",
    "ctypes", "pickle", "marshal", "base64",
}
BANNED_NAMES = {"eval", "exec", "compile", "__import__"}
BANNED_OS_ATTRS = {"system", "popen", "getenv", "putenv", "environ"}
BANNED_METHODS = {"write_text", "write_bytes"}
WRITE_MODE_CHARS = set("wax+")
MAX_SPACELESS_LITERAL = 200


def _open_mode(node: ast.Call):
    """Return the mode argument node of an open() call, or None when it is omitted."""
    if len(node.args) >= 2:
        return node.args[1]
    for kw in node.keywords:
        if kw.arg == "mode":
            return kw.value
    return None


def _is_open_call(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "open"
    return isinstance(func, ast.Attribute) and func.attr == "open"


def scan_source(source: str) -> list:
    """Return a list of violation strings found in `source`."""
    problems = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in BANNED_MODULES:
                    problems.append("import " + alias.name)
        elif isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            if top in BANNED_MODULES:
                problems.append("from %s import" % node.module)
            if top == "os":
                problems.extend("from os import " + a.name for a in node.names if a.name in BANNED_OS_ATTRS)
        elif isinstance(node, ast.Name) and node.id in BANNED_NAMES:
            problems.append("name " + node.id)
        elif isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id == "os" and node.attr in BANNED_OS_ATTRS:
                problems.append("os." + node.attr)
            if node.attr in BANNED_METHODS:
                problems.append("." + node.attr)
        elif isinstance(node, ast.Call) and _is_open_call(node):
            mode = _open_mode(node)
            if mode is not None:
                if not (isinstance(mode, ast.Constant) and isinstance(mode.value, str)):
                    problems.append("open() with non-constant mode")
                elif WRITE_MODE_CHARS & set(mode.value):
                    problems.append("open() mode " + mode.value)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if len(node.value) > MAX_SPACELESS_LITERAL and " " not in node.value:
                problems.append("long spaceless string literal")
    return problems


class ScannerSelfTests(unittest.TestCase):
    def test_flags_bad_code(self):
        bad = [
            "import socket", "import urllib.request", "from http import client", "import subprocess",
            "import pickle", "import base64", "eval('1')", "exec('x')", "compile('x', 'f', 'exec')",
            "__import__('os')", "import os\nos.system('x')", "import os\nos.environ['A']",
            "import os\nos.getenv('A')", "from os import environ", "open('f', 'w')",
            "open('f', mode='a')", "open('f', 'r+')", "open('f', m)", "p.write_text('x')",
            "x = '" + "a" * 201 + "'",
        ]
        for src in bad:
            with self.subTest(src=src[:40]):
                self.assertTrue(scan_source(src), src[:40])

    def test_allows_safe_code(self):
        good = [
            "import re\nre.compile('a')", "import os\nos.walk('.')", "open('f')", "open('f', 'rb')",
            "from pathlib import Path\nPath('x').read_bytes()", "x = 'word ' * 100",
            "def compile_all(): pass", "import fnmatch",
        ]
        for src in good:
            with self.subTest(src=src[:40]):
                self.assertEqual(scan_source(src), [], src[:40])


class ShippedScriptsTests(unittest.TestCase):
    def test_scripts_are_clean(self):
        scripts = sorted(helpers.SCRIPTS.glob("*.py"))
        self.assertTrue(scripts, "no scripts found")
        for path in scripts:
            with self.subTest(script=path.name):
                found = scan_source(path.read_text(encoding="utf-8"))
                self.assertEqual(found, [], "%s: %s" % (path.name, found))


if __name__ == "__main__":
    unittest.main()
