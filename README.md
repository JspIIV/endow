# Endow

**An open-criteria grant that pays the first delivery a round judges to meet the criteria, no committee.** A grantmaking primitive for GenLayer Intelligent Contracts.

A grant is usually decided behind closed doors: someone reads the applications and picks, and the criteria bend to the choice. Endow fixes the criteria first, in public, and lets the work decide. A funder posts plain-language criteria and escrows a reward. Anyone applies by naming one public page that is their delivery: a repo, a demo, a document, whatever the criteria call for. Then anyone can ask the contract to review an application. The contract fetches that applicant's own page and a round of GenLayer validators reads it against the funder's criteria and decides whether it meets them. The first delivery judged to meet the criteria is awarded the reward, and the grant closes.

The evidence is the applicant's own delivery, judged against criteria that were set before any application arrived. The funder cannot move the goalposts after seeing the work, and no reviewer's opinion stands in for the round.

## Interface

- **`open_grant(title, criteria, reward)`** — a funder posts fixed criteria and escrows a reward. Bound to `gl.message.sender_address`. Starts `OPEN`.
- **`apply(grant_id, delivery_url)`** — an applicant names one public page as their delivery. Bound to the caller; a funder cannot apply to their own grant.
- **`review(grant_id, app_index)`** — open to anybody. The contract **fetches that delivery** and a GenLayer round returns `MET` / `UNMET` / `UNCLEAR` against the criteria. The **first** `MET`, while the grant is open, is **awarded** the reward and the grant closes; `UNMET` rejects that application; `UNCLEAR` leaves it to be reviewed again.
- **`award(grant_id)`** — the winner and their delivery, for a payout contract to act on. `balance(address)` — rewards won.

Reads: `status(id)`, `get(id)`, `size()`, `page(start, count)`.

## Why it is fair, and composable

- **Criteria before applications.** The criteria and reward are fixed at open and cannot be edited, so the bar cannot be bent to a favourite after the work is in.
- **Applicant-supplied evidence.** Each applicant brings their own delivery page; the round judges that page against the shared criteria, evenly.
- **First to meet the bar wins, once.** A re-read of state after the round stops a late review from overwriting an already-awarded grant; the reward is paid exactly once, to the applicant, not to whoever triggered the review.
- **No-evidence never pays.** An unrelated, unreadable, or not-found delivery is `UNCLEAR`, never a win.
- **Composable.** `award` and `status` let a payout or milestone contract act on `AWARDED`.

## Why it needs GenLayer

Whether a delivery meets criteria stated in words is a judgement over a real page that no ordinary contract can make and no single reviewer should be trusted with. GenLayer validators each fetch the delivery and reach consensus on one categorical field; the reward is moved by the work against the published criteria, not by a committee.

## Tests

`python tests/endow_rules.py` — the grant rules exercised through the real `open_grant()`, `apply()` and `review()` on an Endow built against a stub of the runtime, with the page and verdict controlled. It proves criteria are judged as published, a funder cannot apply to their own grant, only `MET` awards and only the first one, an unreadable or not-found delivery pays nothing, and an awarded grant is closed. 19 checks.

## Live

- **Contract (GenLayer Asimov):** `0xb77E39E020509d81aeB83F175d3c36a4aBD60D51`
- Explorer: https://explorer-asimov.genlayer.com/address/0xb77E39E020509d81aeB83F175d3c36a4aBD60D51

## Proven on Asimov

`scripts/prove.mjs`, `results/proved.json`. A funder opens a grant (criteria: an open-source CLI that converts CSV to JSON, with a README and an OSI-approved licence) and reward 500; an applicant submits three deliveries:
- a CSV viewer web app with no CLI and no licence (`docs/delivery-bad.txt`) → **UNMET**, the grant stays open.
- an unreadable delivery → `UNCLEAR`, the grant stays open.
- the `csv2json` CLI with a README and an MIT licence (`docs/delivery-good.txt`) → **MET** → `AWARDED`, the reward credited to the applicant, the grant closed.
- a funder cannot apply to their own grant, and a further review after the award is refused.

## Where it stops, plainly

It judges a delivery against criteria in words, which is a judgement, not a proof: write criteria a stranger could apply the same way twice, and accept a delivery a third party can open. It pays the first delivery that meets the bar, not the best one. On Asimov the reward moves as a credited balance rather than native value.

## Licence

AGPL-3.0-or-later.
