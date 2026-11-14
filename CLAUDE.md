# EDH Deck Builder

Builds budget Commander (EDH) decks from a named commander, and upgrades precons into 3 distinct strategies, with primers.

## Rules (always apply)
- Commander format: exactly 100 cards including the commander, singleton (except basic lands and cards that say otherwise), every card inside the commander's colour identity, every card legal in Commander.
- Default budget: US$100 total unless the user names one. For precon upgrades, assume the user already owns the precon: the budget is per upgrade path and covers only cards added from outside it. Use Scryfall prices (USD) as the price source.
- The user's collection (ManaBox CSV export) lives at `collection/manabox.csv` when present. Owned cards cost $0 in every budget and should be preferred when they fit. Budgets cover only cards the user must buy.
- Never invent cards. Every card name must exist on Scryfall, spelled exactly.
- Decklists go in `decks/<commander-slug>.txt`, one card per line as `1 Card Name`, with `# Commander: <name>` at the top.
- Research notes go in `research/<commander-slug>/`. Primers go in `decks/<commander-slug>-primer.md`.
- A hook runs `scripts/validate_deck.py` every time a decklist is saved. If it reports problems, fix them before saying the deck is done.

## Code rules
- Python 3.10+, standard library only.
- Every script uses the `logging` module (no bare print for diagnostics) and has comments throughout.

## Sources
- Card data and prices: Scryfall (https://scryfall.com, API https://api.scryfall.com).
- Popularity / synergy data: EDHREC (https://edhrec.com). Label it as popularity, not proof a card is good.
