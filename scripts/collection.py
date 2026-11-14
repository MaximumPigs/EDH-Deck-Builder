#!/usr/bin/env python3
"""Read a ManaBox collection export (CSV) and list the cards you own.

Export from ManaBox: Collection tab > top-right menu > Export > CSV.
Save it as collection/manabox.csv in this project.

Usage:
  python3 scripts/collection.py names                 # print owned card names
  python3 scripts/collection.py names --out FILE      # write them to FILE
  python3 scripts/collection.py summary               # counts per binder

Standard library only.
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from collections import Counter
from pathlib import Path

logger = logging.getLogger("validate_deck.collection")

# Default location of the collection export, relative to the project root.
PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_COLLECTION = PROJECT_DIR / "collection" / "manabox.csv"

# Columns this module relies on (confirmed from a real ManaBox export, Nov 2026).
REQUIRED_COLUMNS = {"Name", "Quantity"}


def load_collection(path: Path) -> dict[str, int]:
    """Return {lower-case card name: total quantity owned}.

    * Proxies are skipped (they are not real cards you own).
    * Double-faced / split cards ("Far // Away") are also indexed under their
      front-face name ("far"), so a decklist can use either spelling.
    * The same card in several rows (different sets, foils, binders) is summed.
    """
    owned: Counter[str] = Counter()
    # utf-8-sig strips the byte-order mark some exports start with.
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path.name} is missing column(s): {', '.join(sorted(missing))}")

        for lineno, row in enumerate(reader, start=2):  # line 1 is the header
            name = (row.get("Name") or "").strip()
            if not name:
                logger.warning("%s line %d: no card name, skipped", path.name, lineno)
                continue
            if (row.get("Proxy") or "").strip().lower() == "true":
                logger.debug("%s line %d: proxy %r skipped", path.name, lineno, name)
                continue
            try:
                qty = int(row.get("Quantity") or 1)
            except ValueError:
                logger.warning("%s line %d: bad quantity %r, counted as 1", path.name, lineno, row.get("Quantity"))
                qty = 1

            owned[name.lower()] += qty
            # Index the front face of multi-face cards too.
            if " // " in name:
                owned[name.split(" // ")[0].strip().lower()] += qty

    logger.info("Loaded %d distinct owned names from %s", len(owned), path)
    return dict(owned)


def binder_summary(path: Path) -> Counter[str]:
    """Total cards per binder, for a quick sanity check of an export."""
    totals: Counter[str] = Counter()
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            totals[row.get("Binder Name") or "(none)"] += int(row.get("Quantity") or 1)
    return totals


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["names", "summary"])
    parser.add_argument("--file", type=Path, default=DEFAULT_COLLECTION, help="ManaBox CSV export")
    parser.add_argument("--out", type=Path, help="write names to this file instead of stdout")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if not args.file.is_file():
        logger.error("Collection file not found: %s (export it from ManaBox as CSV)", args.file)
        return 2

    if args.command == "summary":
        totals = binder_summary(args.file)
        text = "\n".join(f"{n:>6}  {b}" for b, n in totals.most_common()) + f"\n{sum(totals.values()):>6}  TOTAL"
    else:
        # Original-case names for readability: re-read names from the CSV.
        with args.file.open(encoding="utf-8-sig", newline="") as fh:
            names = sorted({(r.get("Name") or "").strip() for r in csv.DictReader(fh)
                            if (r.get("Proxy") or "").lower() != "true"} - {""})
        text = "\n".join(names)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
        logger.info("Wrote %s", args.out)
    else:
        sys.stdout.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
