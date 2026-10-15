# RoadmapVerdict

RoadmapVerdict dies without GenLayer: no EVM contract can read a GitHub release page and a project blog post on-chain, reason about whether the delivered features match what was promised in a roadmap milestone, and produce a multi-validator consensus verdict — only GenLayer's AI validators can evaluate public evidence during consensus and deliver a tamper-proof delivery record for vesting, prediction markets, and DAO treasury automation.

## Problem

Web3 projects publish roadmaps that promise a mainnet, a mobile app, or a DEX integration by a named quarter. Deadlines slip, and shipped work is often a subset of what was promised. Token holders have no neutral record of whether a milestone was actually delivered.

Vesting schedules, prediction markets, and DAO treasury releases cannot settle fairly when the only input is the team's own claim.

## Solution

RoadmapVerdict accepts a milestone description, a claimed completion date, a project name, and 2 to 5 public evidence URLs. Validators fetch those pages on-chain, compare them to the promised deliverables, and store a permanent verdict: `DELIVERED`, `PARTIALLY_DELIVERED`, or `NOT_DELIVERED`, plus the confirmed items and the gaps.

Remove `web.render` and the LLM and this contract is only a registry of whatever status the submitter typed in. The AI evidence evaluation is the product.

## How it works

1. **Submit.** Anyone calls `submit_milestone(project_name, milestone_description, claimed_completion_date, evidence_urls)`. The report is stored as `PENDING` and the method returns the report id.
2. **Verify.** Anyone calls `verify_milestone(report_id)`. Validators fetch every evidence URL and judge delivery.
3. **Read the verdict.** `get_verdict(report_id)` returns the decision, confidence, reasoning, delivered items, gaps, gap count, and how many sources were readable. `get_report(report_id)` returns the full record.
4. **List.** `list_reports(verdict_filter)` returns matching reports. An empty filter returns every report.

The contract owner can call `invalidate_report(report_id)` on a `PENDING` record. That sets status to `UNVERIFIABLE` and reasoning to `Invalidated by admin`.

## Verdict types

| Verdict | Meaning |
| --- | --- |
| `DELIVERED` | The major deliverables in the milestone are confirmed by readable evidence, and timing is about right. Status becomes `VERIFIED`. |
| `PARTIALLY_DELIVERED` | Some deliverables are confirmed and at least one is missing, incomplete, or significantly late. Status becomes `VERIFIED`. |
| `NOT_DELIVERED` | No meaningful delivery evidence was found, or the evidence contradicts the claim. Status becomes `VERIFIED`. |
| `UNVERIFIABLE` | Fewer than 2 evidence URLs returned readable content, the model output could not be parsed, or the verdict string was not one of the four labels. Status becomes `UNVERIFIABLE`. |

`get_verdict` reverts with `Not yet verified` while status is `PENDING`.

Confidence is an integer from 0 to 100.

A non-`UNVERIFIABLE` verdict requires at least 2 readable evidence sources. One readable page, or none, is not enough to call a milestone delivered or missed.

## Consistency rules

`leader_fn` enforces three rules before the result is returned to consensus:

1. `sources_readable < 2` forces `UNVERIFIABLE`. The count cannot exceed the number of pages that actually returned content, so a model cannot invent extra sources.
2. `PARTIALLY_DELIVERED` with an empty gap list is upgraded to `DELIVERED`.
3. `NOT_DELIVERED` with more confirmed deliverables than gaps is downgraded to `PARTIALLY_DELIVERED`.

`delivered_items` and `gaps` are stored as JSON array strings.

## Consensus design

`verify_milestone` runs inside `gl.vm.run_nondet_unsafe`. Each evidence URL is fetched in its own try/except. A failed fetch becomes text in the prompt. `leader_fn` always returns a dict.

Validators re-run the fetch and the analysis. They agree on the meaning of the delivery decision, not on JSON formatting. Two validators that reach different decisions do not both pass. A leader result of `PARTIALLY_DELIVERED` is rejected when the other validator returns `DELIVERED`, `NOT_DELIVERED`, or `UNVERIFIABLE`, even if both payloads are valid JSON.

- **Verdict exact match.** `DELIVERED`, `PARTIALLY_DELIVERED`, `NOT_DELIVERED`, and `UNVERIFIABLE` must agree exactly.
- **Partial delivery requires a gap.** When the verdict is `PARTIALLY_DELIVERED`, both the leader and the validator must report `gap_count > 0`. Agreeing on the string is not enough. A count of zero on either side rejects the leader.
- **Confidence bands.** Confidence is not compared as an exact integer. The bands are 0-34, 35-79, and 80-100. Both sides must land in the same band. Reasoning text is not compared.

## Use cases

- Vesting schedule automation that releases tokens only after `DELIVERED`
- Prediction market settlement on whether a roadmap item shipped
- DAO treasury release gates tied to a milestone record
- Investor due diligence on a claimed launch date
- Community accountability tracking across quarters

## Supported evidence sources

Public pages the validators can read:

- GitHub release pages
- Announcement blog posts
- Live product URLs
- Announcement posts
- On-chain transaction pages

Each check needs 2 to 5 URLs, and at least 2 of them must return readable content.

## Edge cases handled

- A failed fetch is caught per URL and written into the prompt. The call still finishes.
- An empty or very short page is marked empty and does not count as readable.
- Fewer than 2 readable sources forces `UNVERIFIABLE`, including when the model returns another verdict.
- Malformed model JSON falls back to `UNVERIFIABLE` with confidence 0 and empty arrays.
- An unknown verdict string is normalized to `UNVERIFIABLE`.
- A `delivered_items` or `gaps` value that is not a list is stored as `[]`.
- `PARTIALLY_DELIVERED` with no gaps is upgraded to `DELIVERED`.
- `NOT_DELIVERED` with more delivered items than gaps is downgraded to `PARTIALLY_DELIVERED`.
- Only the owner can invalidate a `PENDING` report. A verified report cannot be invalidated or verified again.

## Deploy on GenLayer Studio (studionet)

1. Open [GenLayer Studio](https://studio.genlayer.com) and create an Intelligent Contract.
2. Paste `contracts/roadmap_verdict.py`. The file header must stay the first lines (`v0.2.16` and the `py-genlayer` dependency). Do not add a frontend.
3. Select network **studionet**.
4. Deploy. The constructor takes no arguments and sets `owner` to the deployer.
5. Call `submit_milestone(project_name, milestone_description, claimed_completion_date, evidence_urls)` with 2 to 5 `http` or `https` URLs.
6. Call `verify_milestone(report_id)`. Then read `get_verdict(report_id)` or `list_reports("")`.

## Run tests

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
pytest tests/test_roadmap_verdict.py -v
```

## Deployment

- **CONTRACT_ADDRESS:** `0x35848B50F8A0F3d4aEeCB0cD7FBa46068Ed66133`
- **NETWORK:** studionet
- **Explorer:** https://explorer-studio.genlayer.com/address/0x35848B50F8A0F3d4aEeCB0cD7FBa46068Ed66133

A read-only `get_count()` call against this address returned `0`. No milestone report is stored on studionet yet, so the worked example below is the expected result from the local test `test_delivered_verdict`, not a receipt from studionet.

### Worked example (expected output, not a live studionet verdict)

Input to `submit_milestone`:

```text
project_name:             SpaceDAO Protocol
milestone_description:    Launch mainnet with staking, bridging, and governance module
claimed_completion_date:  Q1 2026
evidence_urls:
  https://github.com/spacedao/releases/v1.0.0
  https://spacedao.io/blog/mainnet-launch
  https://app.spacedao.io
```

The release page, the launch post, and the live app each describe staking, bridging, and governance as available in March 2026, inside Q1. Expected `get_verdict` after `verify_milestone`:

```json
{
  "report_id": "1",
  "project_name": "SpaceDAO Protocol",
  "milestone_description": "Launch mainnet with staking, bridging, and governance module",
  "claimed_completion_date": "Q1 2026",
  "verdict": "DELIVERED",
  "confidence": 94,
  "reasoning": "All three features confirmed by GitHub release and blog post dated March 2026, within Q1 deadline.",
  "delivered_items": "[\"mainnet launch\", \"staking module\", \"bridging\", \"governance module\"]",
  "gaps": "[]",
  "gap_count": 0,
  "sources_readable": 3
}
```

Status on `get_report` is `VERIFIED`. This output is what the local test asserts when those three pages are readable and the validators agree the milestone was delivered. It is not a transaction result from studionet.
