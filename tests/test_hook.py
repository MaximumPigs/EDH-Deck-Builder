"""Offline tests for .claude/hooks/validate_on_save.py (budget line handling).

Run from the project root:  python3 -m unittest discover tests
"""

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
import test_validate_deck as fixtures  # noqa: E402  (fake Scryfall data)
import validate_deck as vd  # noqa: E402

# Load the hook module from its file path (it lives in a dot-folder).
_spec = importlib.util.spec_from_file_location("validate_on_save", ROOT / ".claude/hooks/validate_on_save.py")
hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hook)


class HookBudgetTests(unittest.TestCase):
    def setUp(self):
        # Route validation through the fake card database instead of Scryfall.
        self._orig = vd.validate
        vd.validate = lambda deck, budget=None, fetch=None: self._orig(deck, budget, fetch=fixtures.fake_fetch)
        self.tmp = tempfile.TemporaryDirectory()
        (Path(self.tmp.name) / "decks").mkdir()

    def tearDown(self):
        vd.validate = self._orig
        self.tmp.cleanup()

    def run_hook(self, deck_text):
        """Write a decklist, feed the hook a PostToolUse payload, return its exit code."""
        path = Path(self.tmp.name) / "decks" / "test.txt"
        path.write_text(deck_text, encoding="utf-8")
        payload = json.dumps({"tool_input": {"file_path": str(path)}})
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            sys.stdin = io.StringIO(payload)
            try:
                return hook.main()
            finally:
                sys.stdin = sys.__stdin__

    def test_budget_line_enforced(self):
        # Deck costs ~US$13.30, so a $5 budget must fail (exit 2).
        self.assertEqual(self.run_hook("# Budget: 5\n" + fixtures.make_deck()), 2)

    def test_budget_none_skips_price_check(self):
        self.assertEqual(self.run_hook("# Budget: none\n" + fixtures.make_deck()), 0)

    def test_rules_still_checked_with_budget_none(self):
        bad = fixtures.make_deck().replace("1 Sol Ring\n98 Mountain", "2 Sol Ring\n97 Mountain")
        self.assertEqual(self.run_hook("# Budget: none\n" + bad), 2)

    def test_non_deck_file_ignored(self):
        payload = json.dumps({"tool_input": {"file_path": str(ROOT / "README.md")}})
        sys.stdin = io.StringIO(payload)
        try:
            self.assertEqual(hook.main(), 0)
        finally:
            sys.stdin = sys.__stdin__


if __name__ == "__main__":
    unittest.main()
