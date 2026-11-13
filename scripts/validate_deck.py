#!/usr/bin/env python3
"""Validate a Commander (EDH) decklist against Scryfall data.

Checks:
  * exactly 100 cards including the commander(s)
  * singleton (except basic lands and "any number" cards)
  * every card inside the commander's colour identity
  * every card legal in Commander
  * total price (Scryfall USD) against an optional budget

Decklist format (plain text):
  # Commander: Card Name        <- one line per commander (partners allowed)
  1 Card Name                   <- quantity + exact card name
  Card Name                     <- quantity defaults to 1

Exit codes: 0 = valid, 1 = problems found, 3 = could not reach Scryfall.
Standard library only.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# ---------------------------------------------------------------------------
# Logging: INFO+ to stderr, DEBUG+ to logs/validate.log next to the project.
# ---------------------------------------------------------------------------
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
logger = logging.getLogger("validate_deck")


def setup_logging(verbose: bool = False) -> None:
    """Configure console and file logging once."""
    if logger.handlers:
        return  # already configured (e.g. imported by the hook)
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    # Console handler: keep it quiet unless --verbose.
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.DEBUG if verbose else logging.WARNING)
    console.setFormatter(fmt)
    logger.addHandler(console)

    # File handler: full detail for debugging later.
    try:
        LOG_DIR.mkdir(exist_ok=True)
        file_handler = logging.FileHandler(LOG_DIR / "validate.log", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except OSError as exc:  # read-only folder etc. - carry on without a file log
        logger.warning("File logging disabled: %s", exc)


# ---------------------------------------------------------------------------
# Scryfall access
# ---------------------------------------------------------------------------
SCRYFALL_COLLECTION_URL = "https://api.scryfall.com/cards/collection"
# Scryfall asks clients to send a User-Agent and Accept header.
HEADERS = {
    "User-Agent": "edh-deck-builder/0.1",
    "Accept": "application/json",
    "Content-Type": "application/json",
}
BATCH_SIZE = 75  # Scryfall's maximum identifiers per collection request
REQUEST_DELAY_S = 0.1  # Scryfall asks for 50-100 ms between requests


class ScryfallError(RuntimeError):
    """Raised when Scryfall cannot be reached or returns an error."""


def fetch_cards_from_scryfall(names: list[str]) -> tuple[dict[str, dict], list[str]]:
    """Look up card names in batches. Returns (found by lower-case name, not_found names)."""
    found: dict[str, dict] = {}
    not_found: list[str] = []
    for start in range(0, len(names), BATCH_SIZE):
        batch = names[start : start + BATCH_SIZE]
        body = json.dumps({"identifiers": [{"name": n} for n in batch]}).encode()
        req = urllib.request.Request(SCRYFALL_COLLECTION_URL, data=body, headers=HEADERS)
        logger.debug("Requesting %d cards from Scryfall", len(batch))
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.load(resp)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise ScryfallError(f"Scryfall request failed: {exc}") from exc

        # Index found cards by every name they answer to (handles double-faced cards).
        for card in payload.get("data", []):
            found[card["name"].lower()] = card
            for face in card.get("card_faces", []):
                found.setdefault(face["name"].lower(), card)
        not_found.extend(item.get("name", "?") for item in payload.get("not_found", []))
        time.sleep(REQUEST_DELAY_S)
    logger.info("Scryfall: %d found, %d not found", len(found), len(not_found))
    return found, not_found


# ---------------------------------------------------------------------------
# Decklist parsing
# ---------------------------------------------------------------------------
COMMANDER_RE = re.compile(r"^#\s*commander:\s*(.+)$", re.IGNORECASE)
CARD_RE = re.compile(r"^(?:(\d+)x?\s+)?(.+?)\s*$")
# Strip export suffixes like "(CMM) 395" or "*F*" that some tools add.
SUFFIX_RE = re.compile(r"\s+\([A-Za-z0-9]{2,6}\)\s*[\w-]*\s*(\*F\*)?$|\s+\*F\*$")


@dataclass
class Decklist:
    """Parsed decklist: commanders plus a name -> quantity map for the 99."""

    commanders: list[str] = field(default_factory=list)
    cards: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        """Total card count including commanders."""
        return len(self.commanders) + sum(self.cards.values())


def parse_decklist(text: str) -> Decklist:
    """Turn decklist text into a Decklist object."""
    deck = Decklist()
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        # Commander header line.
        m = COMMANDER_RE.match(line)
        if m:
            deck.commanders.append(m.group(1).strip())
            continue
        # Any other comment / section header is ignored.
        if line.startswith(("#", "//")):
            continue
        m = CARD_RE.match(line)
        if not m:
            logger.warning("Line %d not understood: %r", lineno, raw)
            continue
        qty = int(m.group(1) or 1)
        name = SUFFIX_RE.sub("", m.group(2)).strip()
        # Don't double-count a commander that is also listed in the 99.
        if name.lower() in (c.lower() for c in deck.commanders):
            logger.info("Line %d: commander %r also in list - ignored", lineno, name)
            continue
        deck.cards[name] = deck.cards.get(name, 0) + qty
    logger.debug("Parsed %d commanders and %d unique cards", len(deck.commanders), len(deck.cards))
    return deck


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
@dataclass
class Report:
    """Validation results."""

    problems: list[str] = field(default_factory=list)
    prices: dict[str, float | None] = field(default_factory=dict)
    total_price: float = 0.0
    unpriced: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def _any_number_allowed(card: dict) -> bool:
    """True for basic lands and cards like Relentless Rats that allow multiples."""
    type_line = card.get("type_line", "")
    oracle = card.get("oracle_text", "") or " ".join(
        f.get("oracle_text", "") for f in card.get("card_faces", [])
    )
    return "Basic" in type_line or "A deck can have any number of cards named" in oracle


def _can_be_commander(card: dict) -> bool:
    """Legendary creatures, or cards whose text says they can be your commander."""
    type_line = card.get("type_line", "")
    oracle = card.get("oracle_text", "") or " ".join(
        f.get("oracle_text", "") for f in card.get("card_faces", [])
    )
    return ("Legendary" in type_line and "Creature" in type_line) or "can be your commander" in oracle


def validate(
    deck: Decklist,
    budget: float | None = None,
    fetch: Callable[[list[str]], tuple[dict[str, dict], list[str]]] = fetch_cards_from_scryfall,
) -> Report:
    """Run all checks. `fetch` is injectable so tests can run offline."""
    report = Report()

    # --- Structure checks that need no card data ---
    if not deck.commanders:
        report.problems.append("No commander found. Add a line '# Commander: <name>'.")
    if deck.total != 100:
        report.problems.append(f"Deck has {deck.total} cards (must be exactly 100 including commander).")

    # --- Look up every card ---
    names = deck.commanders + list(deck.cards)
    found, not_found = fetch(names)
    for name in not_found:
        report.problems.append(f"Card not found on Scryfall (check spelling): {name}")

    # --- Commander checks and combined colour identity ---
    identity: set[str] = set()
    for cmd in deck.commanders:
        card = found.get(cmd.lower())
        if not card:
            continue
        identity |= set(card.get("color_identity", []))
        if not _can_be_commander(card):
            report.problems.append(f"{cmd} cannot be a commander (not a legendary creature).")
    logger.info("Commander colour identity: %s", "".join(sorted(identity)) or "colourless")

    # --- Per-card checks ---
    for name in names:
        card = found.get(name.lower())
        if not card:
            continue
        qty = deck.cards.get(name, 1)

        # Singleton rule.
        if qty > 1 and not _any_number_allowed(card):
            report.problems.append(f"{name} x{qty}: Commander is singleton (only 1 allowed).")

        # Colour identity.
        outside = set(card.get("color_identity", [])) - identity
        if deck.commanders and outside:
            report.problems.append(f"{name} is outside the commander's colour identity ({''.join(sorted(outside))}).")

        # Format legality.
        legality = card.get("legalities", {}).get("commander", "unknown")
        if legality != "legal":
            report.problems.append(f"{name} is {legality} in Commander.")

        # Price: Scryfall's default printing, non-foil USD.
        price_str = (card.get("prices") or {}).get("usd")
        price = float(price_str) if price_str else None
        report.prices[name] = price
        if price is None:
            report.unpriced.append(name)
        else:
            report.total_price += price * qty

    # --- Budget ---
    if budget is not None and report.total_price > budget:
        report.problems.append(f"Over budget: US${report.total_price:.2f} vs US${budget:.2f}.")
    return report


def format_report(deck: Decklist, report: Report, budget: float | None, top: int = 10) -> str:
    """Human-readable summary (also what Claude sees via the hook)."""
    lines = [
        f"Commander(s): {', '.join(deck.commanders) or 'none'}",
        f"Cards: {deck.total}/100",
        f"Total price (Scryfall USD, default printing): US${report.total_price:.2f}"
        + (f" / budget US${budget:.2f}" if budget is not None else ""),
    ]
    priced = sorted(((p, n) for n, p in report.prices.items() if p is not None), reverse=True)
    if priced:
        lines.append(f"Most expensive {min(top, len(priced))}:")
        lines += [f"  US${p:>7.2f}  {n}" for p, n in priced[:top]]
    if report.unpriced:
        lines.append(f"No USD price on Scryfall: {', '.join(report.unpriced)}")
    lines.append("RESULT: VALID" if report.ok else f"RESULT: {len(report.problems)} PROBLEM(S)")
    lines += [f"  - {p}" for p in report.problems]
    return "\n".join(lines)


def run(path: Path, budget: float | None) -> tuple[int, str]:
    """Validate a file; return (exit code, report text). Used by CLI and hook."""
    logger.info("Validating %s (budget=%s)", path, budget)
    deck = parse_decklist(path.read_text(encoding="utf-8"))
    try:
        report = validate(deck, budget)
    except ScryfallError as exc:
        logger.error("%s", exc)
        return 3, f"Could not validate {path.name}: {exc}"
    text = format_report(deck, report, budget)
    logger.info("Result for %s: %s", path.name, "valid" if report.ok else report.problems)
    return (0 if report.ok else 1), text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("decklist", type=Path, help="path to the decklist .txt file")
    parser.add_argument("--budget", type=float, default=None, help="max total price in USD")
    parser.add_argument("-v", "--verbose", action="store_true", help="show debug logging")
    args = parser.parse_args(argv)
    setup_logging(args.verbose)

    if not args.decklist.is_file():
        logger.error("File not found: %s", args.decklist)
        return 2
    code, text = run(args.decklist, args.budget)
    # The report is program output, not a diagnostic, so it goes to stdout.
    sys.stdout.write(text + "\n")
    return code


if __name__ == "__main__":
    sys.exit(main())
