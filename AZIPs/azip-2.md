# AZIP-2: Rollup Gating Contract

## Preamble

| `azip` | `title`                | `description`                                                                                                 | `author`    | `discussions-to`                                          | `status` | `category` | `created`  |
| ------ | ---------------------- | ------------------------------------------------------------------------------------------------------------- | ----------- | --------------------------------------------------------- | -------- | ---------- | ---------- |
| 2    | Rollup Gating Contract | Introduces a gating contract that enforces timelocks and rate-of-change constraints on rollup owner functions | @just-mitch | https://github.com/AztecProtocol/governance/discussions/2 | Draft    | Core       | 2026-03-31 |

## Abstract

This proposal transfers ownership of the current rollup from direct governance control to a Gating Contract that classifies rollup owner functions into two tiers. Critical actions (escape hatch changes, ownership transfers) are subject to a 60-day timelock, giving users and operators a guaranteed long window to react and exit. Operational parameters (reward config, mana target, proving cost, ejection threshold, staking queue config) can be executed immediately after standard governance approval but are subject to per-parameter rate-of-change constraints enforced over time windows, preventing any single governance action — or sequence of actions — from making drastic changes. All future canonical rollups MUST use an equivalent gating mechanism.

## Impacted Stakeholders

**Sequencers** — Sequencers are directly affected by operational parameters gated through this contract, including reward configuration, staking queue config, slasher settings, and ejection thresholds. The rate-of-change constraints protect sequencers from sudden adverse changes to their economic conditions or forced removal from the active set. The 60-day timelock on escape hatch changes preserves their ability to evaluate and respond to changes in fallback block production.

**Provers** — Provers are affected by changes to proving cost per mana and reward configuration. Rate constraints ensure that proving economics cannot be made unviable in a single governance action. The constraint that `rewardDistributor` must never revert protects provers from being unable to claim earned rewards.

**Tokenholders** — Tokenholders benefit from the decoupling of rollup upgrade safety from ordinary governance execution delays. The shorter execution delay for non-rollup governance actions (enabled by this proposal) improves governance agility without weakening rollup protections.

**App Developers** — Application developers benefit from the immutability guarantees on the escape hatch and the bounded nature of fee-related parameter changes. These constraints ensure that deployed applications cannot be rendered unusable by sudden parameter shifts that block L2 transactions, proposing, or proving.

**Infrastructure Providers (RPCs, Block Explorers, Indexers)** — Infrastructure providers benefit from the predictability that rate-constrained parameters provide. Gradual changes are easier to adapt to than sudden shifts. The 60-day timelock on critical changes gives infrastructure operators ample time to prepare for fundamental changes.

## Motivation

### Stage-2 Requirements

L2Beat's classification framework requires that users have roughly 30 days to react and still get an exit transaction included before a governance-triggered rollup change takes effect. If inclusion and exit can pessimistically take up to 20 days, a 60-day timelock still leaves ~40 days of real reaction time — well above the threshold.

The high-level constraint is: **the escape hatch MUST be immutable from the Governance perspective**. This includes hardening all fee change validations that could block L2 transactions, proposing, or proving, as well as immutability of the AZTEC token because it is used as the bond and fee asset.

### Current Limitations

The currently deployed rollup system combines an unnecessarily long governance execution delay with practical mutability vectors in the rollup smart contract. This creates sluggish upgrades on the one hand and short exit windows for users on the other.

Governance currently has access to configuration that can permanently affect the liveness of the rollup:

- `Rollup.setSlasher()` and `Rollup.setLocalEjectionThreshold()`: Set a malicious slasher contract and/or ejection threshold, allowing slashing and ejection of any sequencer
- `Slasher.slash()`: Slash any sequencer and eject them from the set
- Unbounded configuration functions like `Rollup.setRewardConfig(booster, rewardDistributor, ...)`, `Rollup.updateManaTarget(uint.max)`, `Rollup.setProvingCostPerMana(uint.max)`, and `GSE.setProofOfPossessionGasLimit(0)`: Freeze finalization, L2 transactions, and staking respectively by using extreme values
- `Rollup.updateStakingQueueConfig(normalFlushSizeMin=0, normalFlushSizeQuotient=max)`: Stop any new sequencers from joining the active set
- `Rollup.updateEscapeHatch(ADDRESS)`: Use a dead or malicious address to remove the escape hatch guarantee

### Decoupling Concerns

The current approach of encoding rollup protection in the global governance execution delay is problematic because it couples rollup upgrade safety to the pacing of all governance actions, including sequencer withdrawals (whose delay formula includes `executionDelay`). A Gating Contract decouples these concerns:

- **Critical rollup changes** that affect Stage-2 status (escape hatch, ownership) get a 60-day timelock.
- **Operational parameters** (rewards, fees, staking config) can be updated promptly but within bounded ranges enforced over time.
- **Ordinary governance actions** (and sequencer exits) use a shorter execution delay without weakening rollup protection.

Making rollup exits fully immutable provides all users a perpetual exit guarantee, even under comparably short governance execution delays (<30 days).

## Specification

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119 and RFC 8174.

### Gating Contract Deployment

A gating contract SHALL be deployed that becomes the owner of the current rollup. All future canonical rollups SHALL be owned by an equivalent gating contract. The gating contract MUST be configured such that only governance (via approved proposals) can trigger either tier, and no actor can bypass the 60-day delay for critical-tier calls or the rate constraints for operational-tier calls.

### Critical Tier

Critical-tier calls MUST be routed through a timelock with a minimum delay of 60 days (5,184,000 seconds). The flow for critical actions:

```
Governance approves proposal
    → Proposal executes, scheduling action on timelock
    → 60-day timelock delay
    → Action executed on rollup
```

The following functions are classified as critical:

| Function            | Effect                                                     | Constraint                                                                                                                                                                                            |
| ------------------- | ---------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `updateEscapeHatch` | Sets the escape hatch contract (fallback block production) | 60-day timelock. MUST be restricted to only decreasing the escape hatch bond; setting an arbitrary address MUST NOT be permitted. The escape hatch MUST be immutable from the Governance perspective. |
| `transferOwnership` | Transfers ownership of the rollup itself                   | 60-day timelock                                                                                                                                                                                       |

### Operational Tier

Operational-tier calls MAY be executed immediately after governance approval, but the gating contract MUST enforce per-parameter rate-of-change constraints **over time windows** (not per-update). This is critical: constraints MUST be expressed as maximum change per unit of time (e.g., X% per 7 days) so that multiple sequential governance actions (including multicalls) cannot bypass the bounds by splitting a large change into many small updates.

If a proposed parameter change would cause the cumulative change within the current time window to exceed the allowed bound, the call MUST revert.

The following functions are classified as operational:

| Function                    | Effect                                             | Constraint                                                                                                                                                                |
| --------------------------- | -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `setRewardConfig`           | Sequencer/prover reward rates and booster settings | Fee fields: cap of X% per time window. `booster` and `rewardDistributor` MUST be validated to never cause reverts, so that `setRewardConfig()` cannot block finalization. |
| `updateManaTarget`          | Target mana per slot                               | Already constrained (can only increase); additional cap of X% per time window.                                                                                            |
| `setProvingCostPerMana`     | Proving cost per mana unit (fee model input)       | Cap of X% per time window.                                                                                                                                                |
| `setLocalEjectionThreshold` | Minimum stake after slashing before ejection       | Cap of X% per time window.                                                                                                                                                |
| `updateStakingQueueConfig`  | How validators enter the active set                | Individual fields: cap of X% per time window. `normalFlushSizeMin` MUST be enforced to be greater than 0 (minimum flush size of 1).                                       |

> **Note**: The exact constraint values (the "X%" bounds and time windows) are to be determined. The intent is that no governance action or sequence of actions can, for example, set the proving cost per mana to an extreme value, making it impossible to include transactions.

### Additional Constraints

#### Slashing and Ejection

`setSlasher()` MUST be removed from the rollup contract so that governance cannot use slashing to remove all sequencers from the active set in a short period. Further, Governance MUST be removed as an actor that can unilaterally call `Slasher.slash()`.

#### Fee Validation Hardening

All fee-related parameter changes MUST be validated such that they cannot block:
- L2 transaction inclusion
- Block proposing
- Block proving

Parameters that feed into the fee model (`setProvingCostPerMana`, `updateManaTarget`, fee fields in `setRewardConfig`) MUST have their bounds set such that even at the maximum allowed value after a rate-constrained update, the rollup remains functional.

### No Change to Voting Mechanics

This proposal does not modify voting thresholds, quorum requirements, or any other governance approval mechanism.

## Rationale

### Why a Gating Contract Rather Than Longer Governance Delays

The alternative — simply increasing `executionDelay` in the Governance contract — would apply the same delay to all governance actions. This is undesirable because:

1. Sequencer withdrawal delays include `executionDelay` in their formula, making longer delays punitive to honest sequencers.
2. Non-rollup governance actions (treasury operations, parameter changes to non-rollup contracts) do not need 60-day delays.
3. A dedicated gating mechanism cleanly separates rollup safety from governance agility.

### Why Rate-of-Change per Time Rather Than per Update

Multicalls could bypass per-update caps by splitting a large change into many small updates within a single governance action. Expressing constraints as maximum change per time window (e.g., X% per 7 days) makes the bounds robust against any execution pattern.

### Why Escape Hatch Immutability

`updateEscapeHatch` is a vector that could remove the exit guarantee entirely by pointing to a dead or malicious address. Restricting this function to only decreasing the escape hatch bond (rather than changing the escape hatch contract address) preserves the exit guarantee while still allowing governance to make the escape hatch more accessible after the rollup is no longer canonical.

### Why Minimum Flush Size

Without a floor on `normalFlushSizeMin`, governance could set it to 0, preventing any new sequencers from entering the active set. A minimum of 1 ensures the staking queue always processes at least one validator per flush cycle.

## Backwards Compatibility

This proposal introduces backwards incompatibilities:

1. **Rollup ownership transfer**: The current rollup's owner changes from Governance to the Gating Contract. Any existing governance proposals that directly call rollup owner functions will need to target the Gating Contract instead.
2. **Execution timing**: Critical-tier actions will take 60 days longer to execute than they do today. Governance proposals involving these actions must account for the additional delay.
3. **Parameter change limits**: Operational parameters can no longer be changed by arbitrary amounts. Any pending or planned governance proposals that would exceed rate-of-change bounds will need to be split into multiple proposals spaced over time.

These incompatibilities are intentional and constitute the core safety improvement of this proposal.

## Test Cases

Test cases SHOULD cover:

1. **Critical tier timelock enforcement**: A call to `updateEscapeHatch` or `transferOwnership` through the gating contract MUST NOT execute before 60 days have elapsed.
2. **Operational tier rate constraint enforcement**: A call to `setProvingCostPerMana` that exceeds the allowed change within the current time window MUST revert.
3. **Multicall bypass prevention**: Two sequential calls to `setProvingCostPerMana` within the same time window, each within the per-update bound but together exceeding the per-time-window bound, MUST revert on the second call.
4. **Minimum flush size enforcement**: A call to `updateStakingQueueConfig` with `normalFlushSizeMin = 0` MUST revert.
5. **Finalization safety**: Setting `rewardDistributor` to an address whose calls revert MUST be rejected by the gating contract validation.
6. **Access control**: Calls to the gating contract from any address other than Governance MUST revert.

## Security Considerations

### Timelock Bypass

The gating contract MUST NOT have any administrative functions that allow bypassing the 60-day timelock for critical-tier calls. There MUST be no emergency override, multisig backdoor, or upgrade mechanism that could circumvent the delay. The gating contract itself SHOULD be immutable (non-upgradeable).

### Rate Constraint Circumvention

Rate-of-change constraints MUST be enforced cumulatively over time windows, not per-call. The contract MUST track the cumulative change to each parameter within rolling time windows and reject any update that would cause the cumulative change to exceed the bound. This prevents circumvention via multicalls, multiple proposals, or any other batching mechanism.

### Escape Hatch Integrity

The escape hatch is the ultimate user exit guarantee. Any modification to the escape hatch contract address would effectively constitute a change to the trust model. The gating contract MUST ensure that `updateEscapeHatch` cannot point to a non-functional or malicious contract. The RECOMMENDED approach is to restrict this function to only decreasing the escape hatch bond amount.

### Slashing Abuse

Through `setSlasher()` or `Slasher.slash()`, governance could remove all sequencers from the active set, compromising liveness.

### Gating Contract as Single Point of Control

The gating contract becomes the sole owner of the rollup. Its correctness is therefore critical. The contract MUST undergo thorough security auditing before deployment. A bug in the gating contract could either lock out legitimate governance actions or fail to enforce the intended constraints.

### Interaction with Future Rollup Versions

When a new rollup version is deployed via `Registry.addRollup()`, it MUST be deployed with its own gating contract instance. The gating contract parameters (timelock duration, rate bounds) for new rollups SHOULD be at least as restrictive as those specified in this AZIP.

## Copyright Waiver

Copyright and related rights waived via [CC0](/LICENSE).

