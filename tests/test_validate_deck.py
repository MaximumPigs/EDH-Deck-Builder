"""Offline tests for scripts/validate_deck.py (no network needed).

Run from the project root:  python3 -m unittest discover tests
"""

import logging
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import validate_deck as vd  # noqa: E402

logging.getLogger("validate_deck").addHandler(logging.NullHandler())


def card(name, ci, type_line="Artifact", price="1.00", legal="legal", oracle=""):
    """Build a minimal fake Scryfall card object."""
    return {
        "name": name,
        "color_identity": ci,
        "type_line": type_line,
        "oracle_text": oracle,
        "legalities": {"commander": legal},
        "prices": {"usd": price},
    }


# Fake card database standing in for Scryfall.
DB = {
    "krenko, mob boss": card("Krenko, Mob Boss", ["R"], "Legendary Creature — Goblin Warrior", "2.00"),
    "sol ring": card("Sol Ring", [], "Artifact", "1.50"),
    "mountain": card("Mountain", [], "Basic Land — Mountain", "0.10"),
    "counterspell": card("Counterspell", ["U"], "Instant", "1.00"),
    "mana crypt": card("Mana Crypt", [], "Artifact", "150.00", legal="banned"),
    "llanowar elves": card("Llanowar Elves", ["G"], "Creature — Elf Druid", "0.25"),
}


def fake_fetch(names):
    """Mimic fetch_cards_from_scryfall using DB."""
    found = {n.lower(): DB[n.lower()] for n in names if n.lower() in DB}
    missing = [n for n in names if n.lower() not in DB]
    return found, missing


def make_deck(extra_lines=""):
    """Krenko + Sol Ring + 98 Mountains = 100 cards, plus optional extra lines."""
    return "# Commander: Krenko, Mob Boss\n1 Sol Ring\n98 Mountain\n" + extra_lines


class ParseTests(unittest.TestCase):
    def test_counts_commander_and_cards(self):
        deck = vd.parse_decklist(make_deck())
        self.assertEqual(deck.commanders, ["Krenko, Mob Boss"])
        self.assertEqual(deck.total, 100)

    def test_strips_export_suffixes(self):
        deck = vd.parse_decklist("1 Sol Ring (CMM) 395 *F*\n")
        self.assertIn("Sol Ring", deck.cards)


class ValidateTests(unittest.TestCase):
    def check(self, text, budget=None):
        return vd.validate(vd.parse_decklist(text), budget, fetch=fake_fetch)

    def test_valid_deck(self):
        report = self.check(make_deck(), budget=100)
        self.assertTrue(report.ok, report.problems)
        self.assertAlmostEqual(report.total_price, 2.00 + 1.50 + 98 * 0.10)

    def test_wrong_count(self):
        report = self.check(make_deck("1 Llanowar Elves\n"))
        self.assertTrue(any("101 cards" in p for p in report.problems))

    def test_colour_identity(self):
        text = make_deck().replace("98 Mountain", "97 Mountain\n1 Counterspell")
        report = self.check(text)
        self.assertTrue(any("Counterspell is outside" in p for p in report.problems))

    def test_banned_card(self):
        text = make_deck().replace("98 Mountain", "97 Mountain\n1 Mana Crypt")
        report = self.check(text)
        self.assertTrue(any("Mana Crypt is banned" in p for p in report.problems))

    def test_singleton(self):
        text = make_deck().replace("1 Sol Ring\n98 Mountain", "2 Sol Ring\n97 Mountain")
        report = self.check(text)
        self.assertTrue(any("singleton" in p for p in report.problems))

    def test_unknown_card(self):
        text = make_deck().replace("98 Mountain", "97 Mountain\n1 Not A Real Card")
        report = self.check(text)
        self.assertTrue(any("not found" in p for p in report.problems))

    def test_owned_cards_cost_nothing(self):
        # Own Krenko + Sol Ring; only the 98 Mountains (US$9.80) are new.
        owned = {"krenko, mob boss", "sol ring"}
        report = vd.validate(vd.parse_decklist(make_deck()), budget=10, owned=owned, fetch=fake_fetch)
        self.assertTrue(report.ok, report.problems)
        self.assertAlmostEqual(report.total_price, 98 * 0.10)
        self.assertEqual(report.owned_count, 2)

    def test_owned_still_rule_checked(self):
        # Owning a card doesn't make it legal: banned owned card still fails.
        text = make_deck().replace("98 Mountain", "97 Mountain\n1 Mana Crypt")
        report = vd.validate(vd.parse_decklist(text), owned={"mana crypt"}, fetch=fake_fetch)
        self.assertTrue(any("banned" in p for p in report.problems))

    def test_over_budget(self):
        report = self.check(make_deck(), budget=5)
        self.assertTrue(any("Over budget" in p for p in report.problems))


if __name__ == "__main__":
    unittest.main()
