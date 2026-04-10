# AZIP-1: Reduce Governance Execution Delay to 2 Days

## Preamble

| `azip` | `title`                                     | `description`                                                                                                     | `author`    | `discussions-to`                                          | `status` | `category` | `created`  |
| ------ | ------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- | ----------- | --------------------------------------------------------- | -------- | ---------- | ---------- |
| 1      | Reduce Governance Execution Delay to 2 Days | Reduces the governance execution delay from 30 days to 2 days, restoring agility and sequencer capital efficiency | @just-mitch | https://github.com/AztecProtocol/governance/discussions/1 | Draft    | Core       | 2026-03-31 |

## Abstract

This proposal reduces the `executionDelay` parameter in the Governance contract from 30 days to 2 days. The 30-day delay was introduced in the Alpha payload to support L2Beat classification goals, but it does not achieve the intended classification benefit while imposing significant costs on protocol development velocity and sequencer capital efficiency. Rollup-specific protections should be handled by a dedicated gating contract with timelocks (see AZIP-2) or renouncing ownership of the rollup contract entirely (see AZIP-3), not by inflating the global governance delay that applies to all proposals.

## Impacted Stakeholders

**Sequencers** — Sequencers are the most directly affected group. The sequencer withdrawal delay is derived from `executionDelay` via the formula `withdrawalDelay = votingDelay/5 + votingDuration + executionDelay`. Under the current 30-day execution delay, sequencers wait approximately 37.6 days to withdraw their stake. This proposal reduces that to approximately 9.6 days, significantly improving capital efficiency and lowering the barrier to entry and exit for sequencer operators.

**Tokenholders** — Tokenholders benefit from faster execution of governance proposals. Routine governance actions — parameter changes, treasury operations, non-rollup upgrades — currently sit in a 30-day queue before taking effect. Reducing this to 2 days restores the ability to govern the protocol with reasonable responsiveness.

**App Developers** — Application developers benefit indirectly from faster governance cycles. Protocol improvements, standard adoptions, and parameter adjustments that affect the development environment reach execution sooner.

**Provers** — Provers benefit from faster execution of governance actions that affect proving economics (e.g., reward configuration changes), and from the reduced sequencer withdrawal delay which affects the overall validator set dynamics.

## Motivation

### The 30-Day Delay Does Not Achieve Its Goal

The governance execution delay was increased from 7 days to 30 days as part of the Alpha payload, with the goal of achieving stronger rollup classification from L2Beat. However, L2Beat's interpretation requires that users have roughly 30 days to react *and still get an exit transaction included* before a governance-triggered change takes effect. With a pessimistic 20-day inclusion/exit horizon, a 30-day execution delay leaves only ~10 days of real reaction time — insufficient for the classification goal it was meant to achieve.

### Concrete Costs of the Current Delay

The 30-day delay imposes real costs without the intended benefit:

- **Sequencer capital efficiency**: The withdrawal delay formula includes `executionDelay`, so sequencers currently wait ~37.6 days to exit. Reducing to 2 days brings this to ~9.6 days.
- **Protocol development velocity**: Routine governance actions (parameter changes, non-rollup upgrades) wait an entire month before taking effect.

### Separation of Concerns

Protection of the rollup against hasty upgrades should be handled separately via a dedicated timelock on the rollup itself (see AZIP-2 for a Rollup Gating Contract), rather than by inflating the global governance delay. A dedicated gating contract can enforce 60-day timelocks on critical rollup changes while allowing ordinary governance actions to proceed with a shorter delay.

## Specification

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119 and RFC 8174.

### Parameter Change

The `executionDelay` parameter in `Governance.getConfiguration()` SHALL be changed from 30 days (2,592,000 seconds) to 2 days (172,800 seconds).

### Governance Timing Parameters (Reference)

The Governance contract enforces four sequential timing phases for every proposal:

| Phase           | Current Value | Proposed Value     | Description                                                                     |
| --------------- | ------------- | ------------------ | ------------------------------------------------------------------------------- |
| Voting Delay    | 3 days        | 3 days (unchanged) | Buffer after proposal creation before voting opens; power snapshot taken at end |
| Voting Duration | 7 days        | 7 days (unchanged) | Window during which validators vote                                             |
| Execution Delay | 30 days       | **2 days**         | Timelock after acceptance before execution is permitted                         |
| Grace Period    | 7 days        | 7 days (unchanged) | Window during which an accepted proposal can be executed before it expires      |

### Effect on Withdrawal Delay

The sequencer withdrawal delay is derived from these parameters as:

```
withdrawalDelay = votingDelay/5 + votingDuration + executionDelay
```

|         | Current      | Proposed    |
| ------- | ------------ | ----------- |
| Formula | 3/5 + 7 + 30 | 3/5 + 7 + 2 |
| Result  | ~37.6 days   | ~9.6 days   |

### No Other Changes

This proposal does not modify voting delay, voting duration, grace period, quorum requirements, voting thresholds, or any other governance parameter. Only `executionDelay` is changed.

## Rationale

### Why 2 Days

A 2-day execution delay provides sufficient time for stakeholders to prepare for the execution of the payload considering:
- the 10+ days of preceding onchain governance process
- the AZIP/AZUP process should give stakeholders a good understanding of what is in the payload and how to respond

### Why Not 7 Days (the Pre-Alpha Value)

The pre-Alpha value of 7 days would also be an improvement, but the primary rollup protections are being moved to a dedicated gating contract. With that separation in place, the execution delay only needs to be long enough to serve as a basic sanity check window for ordinary governance actions, not as the rollup's exit window.

### Dependency on the Gating Contract AZIP

This proposal is designed to work in conjunction with a Rollup Gating Contract that enforces 60-day timelocks on critical rollup changes. Without the gating contract, reducing the execution delay to 2 days would weaken rollup protection. These two proposals SHOULD be implemented together.

## Backwards Compatibility

This proposal introduces the following backwards incompatibilities:

1. **Shorter execution window**: Proposals that are currently in the Queued state expecting a 30-day delay before execution will need to be handled during the transition. Any proposal queued at the time of this change takes effect will have its remaining delay recalculated under the new parameter.
2. **Shorter withdrawal delay**: Sequencers who planned around the ~37.6 day withdrawal timeline will be able to exit in ~9.6 days. This is a beneficial change with no negative backwards compatibility impact.
3. **Monitoring and alerting**: Any off-chain monitoring systems that assume a 30-day execution delay window for flagging suspicious proposals will need to be reconfigured for the shorter window.

## Security Considerations

### Reduced Reaction Time for Non-Rollup Governance Actions

With a 2-day execution delay, stakeholders have less time to react to non-rollup governance actions (treasury operations, parameter changes to non-rollup contracts) before they take effect. This is acceptable because:

- The full proposal lifecycle still includes voting delay (3 days) + voting duration (7 days) + execution delay (2 days) = 12 days minimum from proposal creation to execution.
- Non-rollup governance actions do not affect users' ability to exit the rollup.
- Stakeholders can observe and oppose proposals during the 10-day voting window.

### Sequencer Withdrawal Timing

The reduced withdrawal delay (~9.6 days instead of ~37.6 days) means governance has less time to react to a sequencer attempting to withdraw before a malicious action. However, the withdrawal delay is designed to ensure that governance can slash misbehaving sequencers before they exit, and a ~9.6 day window is sufficient for governance to create, vote on, and execute a slashing proposal under the new timing parameters.

## Copyright Waiver

Copyright and related rights waived via [CC0](/LICENSE).

