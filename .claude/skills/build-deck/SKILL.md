---
name: build-deck
description: Build a budget Commander/EDH deck and primer from a commander name. Use when the user names a commander and wants a deck built.
argument-hint: "<commander name>" [budget in USD]
arguments: [commander, budget]
---

Build a Commander deck for **$commander** with a total budget of **$budget** USD
(if no budget was given, use the default in CLAUDE.md).

Work in these stages. Pass each role only what it needs: its brief must stand alone.

## 1. Understand the commander
Use the **commander-analyst** subagent. Ask it for the commander's colour identity,
what it rewards, 2-3 viable game plans, and which plan is cheapest to build.
Save its report to `research/<commander-slug>/commander.md`.

## 2. Show the user the plan and confirm
Summarise the game plans in 3-5 dot points, recommend one, and ask the user to
pick before you spend effort on card research. Stop and wait for their answer.

## 3. Find cards (in parallel)
Run **card-scout** subagents in parallel, one per category below, each given the
commander, colour identity, chosen plan, and its share of the budget:
- Ramp (~10 cards) and card draw (~10)
- Removal and interaction (~10) and board wipes (2-3)
- Plan-specific synergy and win conditions (~25-30)
Lands (~36-38, mostly basics plus cheap duals) can be done by you directly.
Save each report to `research/<commander-slug>/`.

## 4. Assemble and price
Merge the lists to exactly 99 cards plus the commander. Write
`decks/<commander-slug>.txt`. The save hook validates it automatically.
Then use the **budget-checker** subagent to find any over-budget cards and
suggest cheaper swaps that keep the plan. Apply swaps and re-save until the
validator passes and the total is within budget.

## 5. Primer
Use the **primer-writer** subagent with the final decklist and the chosen plan.
Save to `decks/<commander-slug>-primer.md`.

## 6. Report back
Give the user: total price, the game plan in 3 lines, the 5 key cards, the file
paths, and anything the agents could not verify.
