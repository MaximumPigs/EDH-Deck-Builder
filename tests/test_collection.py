"""Offline tests for scripts/collection.py and collection-aware pricing.

Run from the project root:  python3 -m unittest discover tests
"""

import logging
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
import collection  # noqa: E402
import test_validate_deck as fx  # noqa: E402  (fake Scryfall data)
import validate_deck as vd  # noqa: E402

logging.getLogger("validate_deck").addHandler(logging.NullHandler())

# Synthetic file with the real ManaBox export header (no personal data).
SAMPLE = ROOT / "tests" / "fixtures" / "manabox_sample.csv"


class LoadCollectionTests(unittest.TestCase):
    def test_quantities_summed_across_rows(self):
        owned = collection.load_collection(SAMPLE)
        self.assertEqual(owned["sol ring"], 3)  # 1 normal + 2 foil

    def test_double_faced_front_face_indexed(self):
        owned = collection.load_collection(SAMPLE)
        self.assertIn("far // away", owned)
        self.assertIn("far", owned)

    def test_proxies_skipped(self):
        self.assertNotIn("mana crypt", collection.load_collection(SAMPLE))

    def test_missing_columns_rejected(self):
        bad = ROOT / "tests" / "fixtures" / "_bad.csv"
        bad.write_text("Card,Qty\nSol Ring,1\n", encoding="utf-8")
        try:
            with self.assertRaises(ValueError):
                collection.load_collection(bad)
        finally:
            bad.unlink()


class CollectionPricingTests(unittest.TestCase):
    def test_csv_accepted_as_owned_source(self):
        owned = vd.load_owned(SAMPLE)
        report = vd.validate(vd.parse_decklist(fx.make_deck()), budget=None, owned=owned, fetch=fx.fake_fetch)
        # Sol Ring is owned (free); Krenko + 98 Mountains must be bought.
        self.assertAlmostEqual(report.total_price, 2.00 + 98 * 0.10)
        self.assertNotIn("Sol Ring", report.prices)

    def test_report_lists_cards_to_buy(self):
        owned = vd.load_owned(SAMPLE)
        deck = vd.parse_decklist(fx.make_deck())
        report = vd.validate(deck, budget=None, owned=owned, fetch=fx.fake_fetch)
        text = vd.format_report(deck, report, None)
        self.assertIn("TO BUY (2 cards)", text)
        self.assertNotIn("Sol Ring", text.split("TO BUY")[1])


if __name__ == "__main__":
    unittest.main()
