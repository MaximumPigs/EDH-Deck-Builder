#!/usr/bin/env python3
"""PostToolUse hook: validate a decklist every time Claude writes or edits one.

Claude Code sends the tool call as JSON on stdin. If the edited file is a
decklist (decks/*.txt), we run the validator. On problems we print the report
to stderr and exit 2, which Claude Code feeds back to Claude so it fixes them.
Any other file: exit 0 silently (no effect, no context cost).
"""

from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

# Make scripts/ importable regardless of where Claude Code runs the hook from.
PROJECT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_DIR / "scripts"))

import validate_deck  # noqa: E402  (import after sys.path tweak)

logger = logging.getLogger("validate_deck.hook")


def read_budget() -> float | None:
    """Pick up the default budget from CLAUDE.md ("Default budget: US$100")."""
    try:
        text = (PROJECT_DIR / "CLAUDE.md").read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r"Default budget:\s*US\$(\d+(?:\.\d+)?)", text)
    return float(m.group(1)) if m else None


def main() -> int:
    validate_deck.setup_logging()

    # Parse the hook payload; never crash Claude's turn on bad input.
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        logger.warning("Hook got non-JSON input: %s", exc)
        return 0

    file_path = (payload.get("tool_input") or {}).get("file_path", "")
    path = Path(file_path.replace("\\", "/"))
    logger.debug("Hook fired for %s", path)

    # Only decklists in decks/ are checked.
    if path.suffix != ".txt" or path.parent.name != "decks" or not path.is_file():
        return 0

    # A budget can be set per deck with a "# Budget: 150" line, or switched off
    # with "# Budget: none" (used for precon upgrades, where only the cost of
    # added cards counts). Otherwise the CLAUDE.md default applies.
    deck_text = path.read_text(encoding="utf-8")
    m = re.search(r"^#\s*budget:\s*\$?(\d+(?:\.\d+)?|none)\s*$", deck_text, re.I | re.M)
    if m and m.group(1).lower() == "none":
        budget = None
        logger.debug("Budget check disabled for %s", path.name)
    elif m:
        budget = float(m.group(1))
    else:
        budget = read_budget()

    # "# Owned: decks/x-original.txt" prices only cards not in that list
    # (so a precon you already own costs nothing). Path is relative to the
    # project folder, or to the decklist's own folder.
    owned_path = None
    m = re.search(r"^#\s*owned:\s*(.+?)\s*$", deck_text, re.I | re.M)
    if m:
        candidate = Path(m.group(1))
        for base in (PROJECT_DIR, path.parent):
            if (base / candidate).is_file():
                owned_path = base / candidate
                break
        else:
            owned_path = PROJECT_DIR / candidate  # run() reports it as missing
        logger.debug("Owned list for %s: %s", path.name, owned_path)

    code, text = validate_deck.run(path, budget, owned_path)
    if code == 0:
        # Valid: tell Claude the result on stdout (shown in transcript), allow.
        print(text)
        return 0
    if code == 3:
        # Scryfall unreachable: warn but don't block the work.
        print(text, file=sys.stderr)
        return 0
    # Problems: exit 2 so Claude receives the report and fixes the deck.
    print(f"Decklist {path.name} failed validation. Fix these before finishing:\n{text}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
