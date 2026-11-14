#!/usr/bin/env python3
"""Look up cards on Scryfall: exact name, colour identity, legality, price.

Subagents use this instead of WebFetch, which Scryfall answers with 403.
It reuses the validator's batched /cards/collection request (same headers,
same rate limit), so up to 75 cards cost one request.

Usage:
  python3 scripts/scryfall_lookup.py "Sol Ring" "Animate Dead"
  python3 scripts/scryfall_lookup.py --file candidates.txt --identity B --oracle

Input names may be plain ("Sol Ring") or decklist lines ("1 Sol Ring");
lines starting with # are ignored in --file.

Output: one line per card:
  Exact Name | identity: B | commander: legal | USD 1.23 | {1}{B} | Creature - Zombie
With --identity, cards outside it are flagged "OUTSIDE IDENTITY".
With --owned FILE (repeatable; decklist, names file or ManaBox CSV), owned
cards are flagged "OWNED".
Not-found names are listed at the end: check spelling, never guess.

Exit codes: 0 = all found, 1 = some not found, 3 = could not reach Scryfall.
Standard library only.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

# Reuse the validator's Scryfall client and owned-list loader rather than
# duplicating them. Both live in this folder.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_deck import (  # noqa: E402
    ScryfallError,
    fetch_cards_from_scryfall,
    load_owned,
    setup_logging,
)

logger = logging.getLogger("validate_deck.lookup")

# "1 Card Name" or "1x Card Name" -> "Card Name"
QTY_RE = re.compile(r"^\d+x?\s+")


def read_names(args: argparse.Namespace) -> list[str]:
    """Collect card names from the command line and --file, de-duplicated in order."""
    raw: list[str] = list(args.names)
    if args.file:
        for line in args.file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                raw.append(line)
    names: list[str] = []
    seen: set[str] = set()
    for item in raw:
        name = QTY_RE.sub("", item.strip())
        if name and name.lower() not in seen:
            seen.add(name.lower())
            names.append(name)
    logger.debug("Looking up %d unique names", len(names))
    return names


def load_owned_names(paths: list[Path] | None) -> set[str]:
    """Load lower-case owned names from decklists, plain name lists or ManaBox CSVs."""
    owned: set[str] = set()
    for path in paths or []:
        if not path.is_file():
            logger.warning("Owned file not found, skipped: %s", path)
            continue
        if path.suffix.lower() == ".csv":
            owned |= load_owned(path)
        else:
            # A names file (one per line) or a decklist: strip quantities.
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    owned.add(QTY_RE.sub("", line).lower())
    return owned


def describe(card: dict, identity: set[str] | None, owned: set[str], oracle: bool) -> str:
    """Format one card as a single summary line (plus oracle text if asked)."""
    ci = card.get("color_identity", [])
    ci_text = "".join(ci) or "C"  # C = colourless
    legal = card.get("legalities", {}).get("commander", "unknown")
    usd = card.get("prices", {}).get("usd")
    price = f"USD {usd}" if usd else "USD none"
    # Double-faced cards keep mana cost / type on their faces.
    faces = card.get("card_faces") or [card]
    # Back faces of transforming cards have no cost, so skip empty ones.
    mana = card.get("mana_cost") or " // ".join(f["mana_cost"] for f in faces if f.get("mana_cost"))
    type_line = card.get("type_line", "")
    parts = [card["name"], f"identity: {ci_text}", f"commander: {legal}", price, mana, type_line]

    # Flags: anything the caller must not miss.
    flags = []
    if legal != "legal":
        flags.append("NOT LEGAL")
    if identity is not None and not set(ci) <= identity:
        flags.append("OUTSIDE IDENTITY")
    if card["name"].lower() in owned or any(f.get("name", "").lower() in owned for f in faces):
        flags.append("OWNED")
    line = " | ".join(parts) + (f" | {' '.join(flags)}" if flags else "")

    if oracle:
        text = card.get("oracle_text") or "\n//\n".join(f.get("oracle_text", "") for f in faces)
        line += "\n    " + text.replace("\n", "\n    ")
    return line


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("names", nargs="*", help="card names (quote names with spaces)")
    parser.add_argument("--file", type=Path, help="file with one card name (or decklist line) per line")
    parser.add_argument("--identity", help="commander colour identity to check against, e.g. B or WUB (C = colourless)")
    parser.add_argument("--owned", type=Path, action="append", help="owned list(s): decklist, names file or ManaBox CSV")
    parser.add_argument("--oracle", action="store_true", help="also print oracle text")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging to stderr")
    args = parser.parse_args(argv)
    setup_logging(args.verbose)
    # Card text uses characters like "−" and "—" that Windows consoles (cp1252)
    # cannot encode; force UTF-8 so printing never crashes.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        logger.debug("Could not reconfigure stdout to UTF-8")

    names = read_names(args)
    if not names:
        parser.error("give card names or --file")

    # "C" means colourless, i.e. an empty identity.
    identity = None
    if args.identity is not None:
        identity = {c for c in args.identity.upper() if c in "WUBRG"}
    owned = load_owned_names(args.owned)

    try:
        found, not_found = fetch_cards_from_scryfall(names)
    except ScryfallError as exc:
        logger.error("%s", exc)
        sys.stderr.write(f"Could not reach Scryfall: {exc}\n")
        return 3

    # Print in input order; `found` is keyed by every lower-case name a card answers to.
    missing = set(n.lower() for n in not_found)
    for name in names:
        card = found.get(name.lower())
        if card is not None:
            print(describe(card, identity, owned, args.oracle))
        elif name.lower() not in missing:
            not_found.append(name)  # e.g. Scryfall matched a different spelling
    if not_found:
        print("NOT FOUND (check spelling, do not guess): " + "; ".join(not_found))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
