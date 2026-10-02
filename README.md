# Endow

**An open-criteria grant that escrows a real reward and pays the first delivery a round judges to meet the criteria.** A grantmaking primitive for GenLayer Intelligent Contracts.

A grant is usually decided behind closed doors, and the criteria bend to the choice. Endow fixes the criteria first, in public, and backs the reward with real value. A funder opens a grant by sending the reward as native value, which the contract holds in escrow. Anyone applies by naming one public page as their delivery. Then anyone can ask the contract to review an application: it fetches that page and a round of GenLayer validators reads it against the funder's fixed criteria. The first delivery judged to meet them is paid the escrowed reward, once, and the grant closes.

The money is real. Opening a grant debits the funder, the escrow is held by the contract, and the winning applicant receives it exactly once through a native transfer. If no one has applied yet, the funder can cancel and take the escrow back.

## Interface

- **`open_grant(title, criteria)`** is **payable**. A funder sends the reward as native value; the reward is exactly the value attached, and the contract holds it in escrow. Bound to `gl.message.sender_address`. Starts `OPEN`. It never raises once value is attached: on any invalid input the value is paid straight back.
- **`apply(grant_id, delivery_url)`** names one public page as the applicant's delivery. Bound to the caller; a funder cannot apply to their own grant.
- **`review(grant_id, app_index)`** is open to anybody. The contract **fetches that delivery** and a GenLayer round returns `MET` / `UNMET` / `UNCLEAR`. The **first** `MET`, while the grant is open, **pays the escrow to that applicant** through `emit_transfer`, exactly once, and the grant closes. `UNMET` rejects that application; `UNCLEAR` leaves it to be reviewed again.
- **`cancel(grant_id)`** lets the funder reclaim the escrow from an open grant that has no applications yet.
- **`award(grant_id)`** returns the winner, the reward and the delivery. Reads: `status(id)`, `get(id)`, `size()`, `page(start, count)`.

## The reward path is real

- **Opening debits the funder.** `open_grant` is payable; the reward is the native value sent and the contract genuinely holds it. A declared amount with no funding cannot exist.
- **The winner is paid, once.** On the first `MET`, the contract transfers the escrow to that applicant via `emit_transfer`, and the terminal `AWARDED` state means it pays exactly once.
- **The funder is never stranded by an invalid open, and can reclaim an unused grant.** An invalid open refunds the value; `cancel` returns the escrow of an open grant with no applications.

## Why it is fair, and composable

- **Criteria before applications.** Criteria and reward are fixed at open and cannot be edited, so the bar cannot be bent to a favourite after the work is in.
- **Applicant-supplied evidence.** Each applicant brings their own delivery page; the round judges it against the shared criteria, evenly.
- **First to meet the bar wins.** A re-read of state after the round stops a late review from overwriting an already-awarded grant.
- **No-evidence never pays.** An unrelated, unreadable, or not-found delivery is `UNCLEAR`, never a win.
- **Composable.** `award` and `status` let a payout or milestone contract act on `AWARDED`.

## Tests

`python tests/endow_rules.py` — the grant rules, with a real escrow, exercised through the real `open_grant()`, `apply()`, `review()` and `cancel()` on an Endow built against a stub of the runtime, with the page, the verdict, and the native value controlled, recording every transfer. It proves opening escrows the value sent, a `MET` verdict pays that escrow to the winner exactly once, an invalid open and a cancel return the value, and an unreadable delivery pays nothing. 28 checks.

## Live and proven

- **On GenLayer Studio (where native value moves):** `0xa219C054Db32E2fec87993C5A9D8d40e5D951Be9`
- **On GenLayer Asimov (identical source):** `0x30D788e6E43a685aB3a87EC8eE77C3925ABf9268` ([explorer](https://explorer-asimov.genlayer.com/address/0x30D788e6E43a685aB3a87EC8eE77C3925ABf9268))

`scripts/prove-studio.mjs`, `results/proved-studio.json`. On Studio, a funder opens a grant by attaching **1 GEN** as the reward:
- opening the grant moves 1 GEN into the contract, held in escrow.
- a CSV viewer with no CLI and no licence (`docs/delivery-bad.txt`) is reviewed to **UNMET**, the grant stays open.
- the `csv2json` CLI with a README and an MIT licence (`docs/delivery-good.txt`) is reviewed to **MET**: the grant is `AWARDED` and the **winner's on-chain balance rises by exactly 1 GEN** while the contract's balance returns to 0.
- a second funded grant is cancelled by the funder and the escrow is returned.

The value path is demonstrated on Studio because native value transfers do not execute on the Asimov testnet (measured: the contract's bookkeeping is correct but no balance moves). The source deployed to both networks is identical to this repository.

## Where it stops, plainly

It judges a delivery against criteria in words, which is a judgement, not a proof: write criteria a stranger could apply the same way twice, and accept a delivery a third party can open. It pays the first delivery that meets the bar, not the best one.

## Licence

AGPL-3.0-or-later.
