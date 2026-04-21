# Aztec Improvement Proposal: Optimize Prover Rewards for Consistency

## Preamble

| `azip` | `title` | `description` | `author` | `discussions-to` | `status` | `category` | `created` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 5 | Optimize Prover Rewards for Consistency | Retunes `RewardBooster` parameters to penalize inconsistent provers and favor committed operators. | Emre (@EmrePiconbello) | https://forum.aztec.network/t/proposal-optimizing-prover-rewards-for-more-consistency/8528 | Draft | Core | 2026-04-21 |

> AZIP number is a placeholder — to be assigned by an editor upon submission.

## Abstract

Current `RewardBooster` parameters produce a reward curve flat enough that a prover at ~78% epoch coverage still captures ~44% of maximum rewards. This lets inconsistent operators cherry-pick cheap epochs and erodes the economics of committed provers. This AZIP retunes four `RewardBooster` parameters (`increment`, `maxScore`, `a`, `minimum`) so that the break-even point moves to ~98.6% coverage and misses cascade sharply. No contract code changes.

Full problem analysis, simulations, and discussion: see [the forum thread](https://forum.aztec.network/t/proposal-optimizing-prover-rewards-for-more-consistency/8528).

## Impacted Stakeholders

**Provers** — Primary stakeholder. Consistent, committed provers see higher relative rewards; intermittent provers see a steep drop. Legitimate outages remain recoverable (single-miss recovery in ~71 epochs).

**Sequencers / Tokenholders** — Indirect. Healthier prover economics support sustained proving throughput as application load grows.

## Motivation

See the [forum post](https://forum.aztec.network/t/proposal-optimizing-prover-rewards-for-more-consistency/8528) for the full motivation. Summary:

- The current curve under-penalizes low coverage, enabling cherry-picking of cheap epochs.
- As hardware costs rise with network load, dedicated operators cannot compete with opportunistic ones under the existing curve.
- The share formula `share = max(k - a * (maxScore - score)² / 1e10, minimum)` is retained; only its parameters are retuned.

## Specification

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119 and RFC 8174.

The following `RewardBooster` parameters SHALL be updated:

| Parameter   | Current     | Proposed |
| ----------- | ----------- | -------- |
| `increment` | 125,000     | 101,400  |
| `maxScore`  | 15,000,000  | 367,500  |
| `a`         | 1,000       | 250,000  |
| `minimum`   | 100,000     | 10,000   |

No other parameters, contracts, or formulas are modified.

## Rationale

Derivation, edge-case simulations, and alternative parameter sets considered are documented in the [forum thread](https://forum.aztec.network/t/proposal-optimizing-prover-rewards-for-more-consistency/8528). Headline effects:

- Break-even coverage: ~98.6% (up from ~78%).
- Score-maximum cascade: 0 misses → 100%, 1 miss → ~75%, 2+ consecutive → ~1%.
- Recovery: single miss → ~71 epochs; zero → max → ~262 epochs (~7 days).

## Backwards Compatibility

Fully backwards compatible. The change is configuration-only; no ABI, storage layout, or contract code is modified. Provers and indexers relying on absolute reward magnitudes SHOULD refresh expectations against the new curve.

## Economics Considerations

The proposal redistributes — not inflates — prover rewards. Total emissions are unchanged; share among provers shifts toward those maintaining high epoch coverage. Detailed scenario tables are in the [forum thread](https://forum.aztec.network/t/proposal-optimizing-prover-rewards-for-more-consistency/8528).

## Security Considerations

- **No smart-contract risk**: configuration-only change, no new code paths.
- **Protocol-wide outages**: affect all provers equally; relative economic positions preserved.
- **Parameter miscalibration**: if the new curve proves too aggressive in practice, governance can re-tune via the same mechanism.
- **Collusion / centralization**: the steeper curve marginally raises the baseline coverage required to be profitable, which could advantage well-capitalized operators. Mitigated by the recovery window preserving a viable path for smaller committed provers.

## Copyright Waiver

Copyright and related rights waived via [CC0](/LICENSE).
