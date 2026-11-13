---
name: upgrade-deck
description: Upgrade a Commander/EDH preconstructed (precon) deck - finds 3 upgrade paths with different strategies. Use when the user names a precon and wants it upgraded.
argument-hint: "<precon name>" [budget per path in USD]
arguments: [precon, budget]
---

Upgrade the Commander precon **$precon**. Each upgrade path may spend up to
**$budget** USD on new cards (if no budget was given, use the default in CLAUDE.md).

**Pricing assumes the user already owns the precon.** Cards from the precon cost
$0; only cards added from outside it count toward the budget. Cut cards give no
refund.

Pass each role only what it needs: its brief must stand alone.

## 1. Get the precon
Use the **precon-analyst** subagent. It finds the official decklist, the face
commander (and any alternate commanders in the box), and its weaknesses.
- Save the list to `decks/<precon-slug>-original.txt` with a `# Budget: none` line
  at the top (the save hook validates it but skips the total-price check).
- Save the report to `research/<precon-slug>/precon.md`.
If the precon cannot be identified (e.g. the name is ambiguous), ask the user to
choose between the closest matches and stop until they answer.

## 2. Pick 3 distinct strategies
From the analyst's report, choose 3 upgrade paths that play **differently** from
each other (for example: go-wide tokens vs. voltron vs. aristocrats). They may use
the face commander or an alternate commander from the box. For each, write one
line: commander, strategy, how it wins. If two paths would share more than about
a third of their adds, replace one.

## 3. Build the 3 paths (in parallel)
Run 3 **upgrade-strategist** subagents in parallel, one per path. Give each:
the original decklist path, the commander, its colour identity, its one-line
strategy, the budget, and the other two strategies (so it stays distinct).
Each returns a cut/add list. Save each report to `research/<precon-slug>/path-<n>.md`.

## 4. Write and check the decklists
For each path, apply its cuts and adds to the original list and write
`decks/<precon-slug>-path-<n>-<strategy-slug>.txt` with these lines at the top:
```
# Commander: <commander>
# Budget: <budget>
# Owned: decks/<precon-slug>-original.txt
```
The `# Owned:` line makes the validator price only cards NOT in the precon, so
the budget check covers new cards only. The save hook validates each list; if
it fails (including over budget), use the **budget-checker** subagent on that
path, apply its swaps, and re-save.

## 5. Compare and let the user choose
Write `decks/<precon-slug>-upgrades.md` with a comparison table:
Path | Commander | Strategy | Cards changed | Cost of adds | Plays like | Best for.
Show the table to the user, recommend one, and ask which they want a primer for.

## 6. Primer
When the user picks, use the **primer-writer** subagent on that path's decklist and
research note. Save to `decks/<precon-slug>-path-<n>-primer.md`.

## Report back
Give the user: the 3 paths in one line each, the cost of each, file paths, and
anything the agents could not verify.
