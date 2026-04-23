# AZUP-1: Cut the Leash

## Preamble

| `azup` | `title`       | `description`                                                                         | `author`    | `azips-included`                                                                                                           | `discussions-to` | `created`  |
| ------ | ------------- | ------------------------------------------------------------------------------------- | ----------- | -------------------------------------------------------------------------------------------------------------------------- | ---------------- | ---------- |
| 1      | Cut the Leash | Reduces governance execution delay to 2 days and renounces ownership of the v4 rollup | @just-mitch | [AZIP-1](https://github.com/AztecProtocol/governance/pull/4), [AZIP-3](https://github.com/AztecProtocol/governance/pull/6) | None             | 2026-04-10 |

## Abstract

This upgrade package bundles two governance actions. First, [AZIP-1](../AZIPs/azip-1.md) reduces the governance execution delay from 30 days to 2 days, restoring protocol agility and improving sequencer capital efficiency. Second, [AZIP-3](../AZIPs/azip-3.md) renounces ownership of the v4 rollup at `0xAe2001f7e21d5EcABf6234E9FDd1E76F50F74962`, rendering it fully immutable and qualifying it as Stage 2 from L2Beat's perspective. Together, these actions decouple rollup safety from governance pacing: the rollup becomes trustless through immutability, while governance becomes responsive through a shorter delay.

## Motivation

The current 30-day governance execution delay was introduced to support L2Beat classification goals, but it does not achieve the intended classification benefit while imposing significant costs on sequencer capital efficiency and protocol development velocity. Meanwhile, the v4 rollup remains mutable through governance — a trust assumption that prevents Stage 2 classification.

This upgrade resolves both issues simultaneously. Renouncing rollup ownership eliminates the need for a long governance delay as a rollup protection mechanism, and reducing the delay restores governance responsiveness now that rollup safety is guaranteed by immutability rather than slowness.

## Specification

### 1. Payload / Action Details

**Action 1: Reduce Governance Execution Delay (AZIP-1)**

| Item         | Value                                                         |
| ------------ | ------------------------------------------------------------- |
| **Contract** | Governance                                                    |
| **Function** | `updateExecutionDelay(172800)`                                |
| **Effect**   | Sets execution delay from 30 days to 2 days (172,800 seconds) |

**Action 2: Renounce v4 Rollup Ownership (AZIP-3)**

| Item         | Value                                                                        |
| ------------ | ---------------------------------------------------------------------------- |
| **Contract** | Rollup v4 (`0xAe2001f7e21d5EcABf6234E9FDd1E76F50F74962`)                     |
| **Function** | `renounceOwnership()`                                                        |
| **Effect**   | Transfers ownership to `address(0)`, making the rollup permanently immutable |

### 2. Sequencer Configuration (for signaling)

Sequencers should set the payload address for signaling once the proposal contract is deployed. Details will be updated here when available.

## Impact Evaluation

**Sequencers** — Withdrawal delay drops from ~37.6 days to ~9.6 days, significantly improving capital efficiency. All v4 rollup parameters become permanently fixed — no future governance action can alter reward config, staking queue, or ejection thresholds.

**Provers** — Proving cost per mana and reward configuration on v4 become immutable. Governance actions affecting prover economics on other contracts execute faster.

**Tokenholders** — Governance proposals execute in 2 days instead of 30, restoring responsiveness. Control over the v4 rollup is permanently relinquished.

**App Developers & Infrastructure Providers** — The v4 rollup becomes fully predictable. No parameter changes, no surprises.

## Security & Audits

**Execution delay reduction**: The 2-day delay is sufficient for non-rollup governance actions. Rollup-specific protections are no longer needed in the governance delay because the v4 rollup will have no owner.

**Ownership renunciation**: `renounceOwnership()` is inherited from OpenZeppelin's `Ownable` — a widely audited and battle-tested implementation. The call is irreversible by design. All current rollup parameters should be reviewed and confirmed as suitable for permanent operation before this proposal is executed.

**Ordering**: Both actions can be executed atomically in a single proposal. The order does not matter — neither action depends on the other.

## Open Questions and Feedback

- Are the current v4 rollup parameters (reward config, mana target, proving cost, ejection threshold, staking queue config) suitable for permanent operation?
- Should this AZUP wait for any pending parameter adjustments to land before renouncing ownership?

## Copyright Waiver

Copyright and related rights waived via [CC0](/LICENSE).
