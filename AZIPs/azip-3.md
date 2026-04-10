# AZIP-3: Renounce Ownership of v4 Rollup

## Preamble

| `azip` | `title`                                                                      | `description`                                                                 | `author`    | `discussions-to`                                          | `status` | `category` | `created`  |
| ------ | ---------------------------------------------------------------------------- | ----------------------------------------------------------------------------- | ----------- | --------------------------------------------------------- | -------- | ---------- | ---------- |
| 3      | Renounce ownership of v4 rollup (0xAe2001f7e21d5EcABf6234E9FDd1E76F50F74962) | Governance renounces ownership of the v4 rollup, rendering it fully immutable | @just-mitch | N/A                                                       | Draft    | Core       | 2026-04-10 |

## Abstract

This proposal directs Governance to call `renounceOwnership()` on the v4 rollup contract at `0xAe2001f7e21d5EcABf6234E9FDd1E76F50F74962`. The rollup inherits OpenZeppelin's `Ownable`, so this call transfers ownership to the zero address, permanently removing any ability for Governance — or any other actor — to modify the rollup's configuration. This renders the escape hatch, operational parameters, and all owner-gated functions fully immutable, which should qualify the rollup as Stage 2 from L2Beat's perspective.

## Impacted Stakeholders

**Sequencers** — After ownership is renounced, no governance action can alter reward configuration, staking queue parameters, ejection thresholds, or the slasher. Sequencers gain certainty that their economic conditions cannot be changed, but lose the ability to have operational parameters adjusted through governance if conditions warrant it.

**Provers** — Proving cost per mana and reward configuration become permanently fixed. Provers benefit from predictability but cannot have parameters adjusted if proving economics change materially.

**Tokenholders** — Tokenholders lose governance control over the v4 rollup entirely. This is a deliberate tradeoff: the rollup becomes credibly neutral and immutable at the cost of any future governance-driven upgrades to v4.

**App Developers** — Application developers gain the strongest possible guarantee that the rollup's behavior will not change. Fee parameters, transaction inclusion rules, and the escape hatch are permanently fixed.

**Infrastructure Providers (RPCs, Block Explorers, Indexers)** — Infrastructure providers benefit from full immutability. No parameter changes means no operational surprises.

## Motivation

### Stage-2 Requirements

L2Beat's Stage 2 classification requires that users have a guaranteed exit window and that the rollup cannot be unilaterally modified by a trusted party. While a gating contract with timelocks and rate constraints (as proposed in AZIP-2) provides strong protections, renouncing ownership entirely eliminates governance as a trust assumption. With no owner, there is no party that can modify the rollup — the escape hatch and all parameters are immutable by construction.

### Simplicity

Renouncing ownership is the simplest possible path to immutability. It requires a single governance action — calling `renounceOwnership()` — with no new contracts to deploy, audit, or maintain.

## Specification

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119 and RFC 8174.

Governance MUST execute a proposal that calls `renounceOwnership()` on the v4 rollup contract at `0xAe2001f7e21d5EcABf6234E9FDd1E76F50F74962`. This function is inherited from OpenZeppelin's `Ownable` contract and transfers ownership to `address(0)`.

After execution, all functions on the rollup contract that are gated by the `onlyOwner` modifier MUST revert when called by any address, including the previous owner.

### No Change to Voting Mechanics

This proposal does not modify voting thresholds, quorum requirements, or any other governance approval mechanism.

## Rationale

### Why Renounce Rather Than Transfer to a Gating Contract

The v4 rollup is expected to be shortlived, and so can tolerate immutability. The v5 rollup will have the gating contracts (see AZIP-2) to provide mutability within stage 2 requirements. 

### Why This Is Irreversible

`renounceOwnership()` sets the owner to `address(0)`. There is no mechanism to reclaim ownership. This is the point: irreversibility is what makes the immutability guarantee credible.

## Backwards Compatibility

This proposal introduces backwards incompatibilities:

1. **All owner-gated functions become uncallable.** Any existing or future governance proposals that target owner functions on the v4 rollup will fail. This includes `setRewardConfig`, `updateManaTarget`, `setProvingCostPerMana`, `setLocalEjectionThreshold`, `updateStakingQueueConfig`, `transferOwnership`, and any other `onlyOwner` function.
2. **No parameter adjustments.** If operational conditions change (e.g., proving costs shift significantly), there is no governance mechanism to adjust the v4 rollup's parameters. The only recourse is to deploy a new rollup version.

These incompatibilities are intentional and constitute the core immutability guarantee of this proposal.

## Test Cases

Test cases SHOULD cover:

1. **Ownership renounced**: After the proposal executes, `owner()` on the rollup contract MUST return `address(0)`.
2. **Owner functions revert**: Calls to any `onlyOwner` function on the rollup MUST revert after ownership is renounced.
3. **Escape hatch unaffected**: The escape hatch MUST remain functional after ownership is renounced.
4. **Normal operation unaffected**: Block proposing, proving, and transaction inclusion MUST continue to function normally after ownership is renounced.

## Security Considerations

### Irreversibility

This action is permanent. Once ownership is renounced, there is no mechanism to restore it. Any bugs in the rollup's current parameter configuration become permanent. This proposal SHOULD only be executed after thorough review confirms that all parameters are correctly set for long-term operation.

### Parameter Ossification

All fee-related parameters, reward configuration, staking queue settings, and ejection thresholds become fixed at their current values. If any of these values are suboptimal, they cannot be corrected. The rollup's current parameter state MUST be audited before this proposal is executed.

### Escape Hatch Integrity

The escape hatch contract address and bond amount are already immutable per rollup. Renouncing ownership does not change this — it provides an additional layer of assurance by removing the owner entirely, eliminating any theoretical attack surface through owner-gated functions.

### Interaction with Future Rollup Versions

This proposal only affects the v4 rollup at `0xAe2001f7e21d5EcABf6234E9FDd1E76F50F74962`. Future rollup versions deployed via `Registry.addRollup()` are unaffected and will have their own ownership configuration.

## Copyright Waiver

Copyright and related rights waived via [CC0](/LICENSE).
