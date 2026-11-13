# EDH Deck Builder (Claude Code project)

Name a commander, and Claude's agent roles research, build, price and validate a
budget Commander deck, then write a primer for it.

## Setup (once)
1. Install Claude Code (needs a paid Claude plan): https://code.claude.com/docs/en/overview
2. Download this folder and open a terminal in it.
3. Run `claude`. Accept the prompt to trust the folder (this turns on the hook and permissions).
4. Needs Python 3.10+ on your computer (for the validator).

## Use it
```
/build-deck "Krenko, Mob Boss" 100
```
- 1st argument: commander name (in quotes if it has spaces or commas)
- 2nd argument: budget in USD (optional, default in CLAUDE.md)

Claude will show you game plans and ask you to pick one, then build the deck.

Output:
- `decks/<commander>.txt` - the decklist (paste into Moxfield/Archidekt)
- `decks/<commander>-primer.md` - how to play it
- `research/<commander>/` - what the agents found

## What's in here and why

| Piece | File | What it does |
|---|---|---|
| Always-on rules | `CLAUDE.md` | Format rules, budget, file locations |
| Skill | `.claude/skills/build-deck/SKILL.md` | The step-by-step playbook behind `/build-deck` |
| Role | `.claude/agents/commander-analyst.md` | Works out the commander's game plans |
| Role | `.claude/agents/card-scout.md` | Finds cards for one category (run in parallel) |
| Role | `.claude/agents/budget-checker.md` | Prices the deck and suggests cheaper swaps (cheap model) |
| Role | `.claude/agents/primer-writer.md` | Writes the how-to-play guide (can't browse) |
| Hook | `.claude/settings.json` + `.claude/hooks/validate_on_save.py` | Every time a decklist is saved, checks 100 cards, singleton, colour identity, bans and budget. Problems go straight back to Claude to fix |
| Script | `scripts/validate_deck.py` | The checker. Run it yourself too: `python3 scripts/validate_deck.py decks/x.txt --budget 100` |

## Notes
- Prices are Scryfall's USD price for its default printing, so the cheapest printing may cost less.
- The validator needs internet access to reach Scryfall.
- Logs: `logs/validate.log`. Tests (offline): `python3 -m unittest discover tests`.
