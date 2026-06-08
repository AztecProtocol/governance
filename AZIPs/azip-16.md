# AZIP-16: Activate Equivocation Slashing and Update Economic Parameters

## Preamble

| `azip` | `title` | `description` | `author` | `discussions-to` | `status` | `category` | `created` | `requires` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 16 | Activate Equivocation Slashing and Update Economic Parameters | Activates equivocation penalties, splits SMALL/MEDIUM/LARGE slash units, halves `provingCostPerMana`, and enables a new checkpoint offense. | Amin Sammara (@aminsammara, amin@aztec-labs.com) | N/A | Accepted | Economics | 2026-05-26 | AZIP-7 |

## Abstract

This AZIP fixes the values of the slashing and fee-market parameters that the v5 release will ship with. The changes fall into three groups. **(1)** Activate the two equivocation offenses (`DUPLICATE_PROPOSAL` and `DUPLICATE_ATTESTATION`), which were specified earlier but configured with a zero penalty in v4 while detection paths were burned in. **(2)** Revise the L1 slashing-unit amounts (`SLASH_AMOUNT_SMALL`, `SLASH_AMOUNT_MEDIUM`, `SLASH_AMOUNT_LARGE`) so that more harmful offenses can be penalized more heavily than less harmful ones. **(3)** Reduce `provingCostPerMana` by 50% to track the prover-cost reduction shipped in v5. This AZIP additionally activates one of the new offenses introduced by [AZIP-7](./azip-7-update_slashing.md), `BROADCASTED_INVALID_CHECKPOINT_PROPOSAL`, while keeping the other new offenses at zero through this release cycle.

## Impacted Stakeholders

**Validators.** Effective slashing exposure increases for two existing offenses (equivocation on proposals and on attestations) and for one new offense (invalid checkpoint proposal). Validators who currently treat the zero-valued penalties as "won't actually slash" MUST update their operational posture once they upgrade to v5 software. The split between SMALL and MEDIUM/LARGE means a single MEDIUM- or LARGE-classified offense now removes a larger fraction of bonded stake than before, although the `localEjectionThreshold` is unchanged so the operator's existing ejection model is preserved.

**Node Operators.** Activation is implicit in the v5 upgrade: the v5 client ships with the new defaults baked in, so operators who upgrade to v5 software automatically pick up the activated penalties. No per-operator configuration change is required. Operators SHOULD review their alerting on `DUPLICATE_PROPOSAL`, `DUPLICATE_ATTESTATION`, and `BROADCASTED_INVALID_CHECKPOINT_PROPOSAL` offense counters before cutting over, because previously the first two counters were informational only and after the v5 cutover they correspond to real economic events.

**Provers.** `provingCostPerMana` directly feeds the fee market's proving subsidy. Halving it reduces the per-mana reward provers receive from priority fees. The change is justified by an approximate 50% reduction in v5 proving compute and a 50% reduction in L1 verification gas, so prover unit economics SHOULD remain neutral or slightly favorable. Provers operating under contracts that price proving in protocol-denominated units MUST update their accounting at the v5 cutover.

**Sequencers.** No direct change to sequencer responsibilities. The lower `provingCostPerMana` slightly reduces the proving overhead component of base fees, marginally increasing sequencer revenue at constant gas consumption.

## Motivation

### Activating equivocation penalties

The Aztec v4 client introduced two equivocation offenses with their penalty set to zero. The intent was to allow time to observe the corresponding watchers and detection paths in production before applying real economic consequences. To the best of the author's knowledge, no `DUPLICATE_PROPOSAL` or `DUPLICATE_ATTESTATION` offense has been detected on the P2P network during the Alpha phase of operation.

Under v5 the cost of equivocation to network liveness rises significantly. With pipelined block-building, a proposer that equivocates leaves the *next* proposer unable to determine which view of the chain is canonical, producing multi-slot liveness failures. Equivocation is unambiguously detectable from on-network evidence (two signed messages by the same key, same slot) and there is no honest behavior that produces it. Continuing to assign it a zero penalty understates its actual cost to the network.

### Differentiating SMALL, MEDIUM, and LARGE slash amounts

In v4, all three slashing unit amounts (`SLASH_AMOUNT_SMALL`, `SLASH_AMOUNT_MEDIUM`, `SLASH_AMOUNT_LARGE`) are set to `2_000n`. The decision at the time was that there was no operational basis for a ranking between non-zero offenses and that uniformity reduced configuration risk.

Activating equivocation slashing changes that calculus. Equivocation is more harmful than other currently-slashable behaviors (it directly breaks pipelined liveness), so the unit-mapping framework should be able to express that ranking. Keeping `SMALL` unchanged while raising `MEDIUM` and `LARGE` preserves backward semantics for existing offenses while allowing equivocation and similar high-impact offenses to be penalized meaningfully.

### Reducing `provingCostPerMana`

The v5 release substantially reduces proving cost in two places. First, end-to-end prover compute time per epoch is approximately 50% lower than v4 (driven by the Chonk circuit optimizations catalogued in [AZIP-13](./azip-13.md)). Second, on-L1 proof verification gas drops from approximately 3.6M to 1.8M gas with the new verifier contract.

`provingCostPerMana` was set for v4 economics. Carrying the v4 value forward into the v5 rollup deployment would overstate the cost of proving and inflate the proving-subsidy component of base fees relative to actual prover unit costs. The v5 rollup MUST therefore be deployed with a value that reflects the new cost structure.

### Activating `BROADCASTED_INVALID_CHECKPOINT_PROPOSAL`

[AZIP-7](./azip-7-update_slashing.md) introduces three new checkpoint-related offenses. The author proposes activating one of them with this AZIP — the proposer-side `BROADCASTED_INVALID_CHECKPOINT_PROPOSAL` — and keeping the remaining two (attesting to an invalid proposal, submitting block proposal after checkpoint) at zero until they have a deployment cycle of observed behavior. Rationale is given under Specification.

### Keeping `DATA_WITHHOLDING` disabled

The `DATA_WITHHOLDING` offense existed in v4 but its penalty was set to `0` in the deployed configuration while the detection mechanism was being established. [AZIP-7](./azip-7-update_slashing.md) replaces the earlier _Epoch Pruned_ heuristic with a per-checkpoint check at `slotStart(checkpoint.slot + SLASH_DATA_WITHHOLDING_TOLERANCE_SLOTS + 1)`: if any tx referenced by the checkpoint's blocks is still missing locally at that point, the checkpoint's attesters are charged with data withholding. The watcher that implements this check is itself new code in the v5 lineage.

The author proposes carrying the `0` setting forward into v5 for two reasons. First, the detection path is materially new: shifting from "wait for epoch proving to fail" to "probe the local mempool a few slots after the checkpoint" changes both the timing and the false-positive surface of the offense. Second, the tolerance window (`SLASH_DATA_WITHHOLDING_TOLERANCE_SLOTS = 3`) is calibrated against expectations about tx propagation speed in the p2p mesh, and those expectations have not yet been validated against production traffic at v5 scale. Activating slashing before the network has accumulated tx-propagation-latency data risks penalizing honest committees during transient p2p congestion. Keeping the penalty at `0` through v5 defers activation until the tolerance has been empirically confirmed.

## Specification

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119 and RFC 8174.

All parameter values specified below are deployment-time values for the v5 release. There is no in-band governance switch to flip them after deployment; activation coincides with the v5 cutover.

### Activated penalties (previously zero)

The following node-side slashing parameters MUST ship as defaults in the v5 client at the indicated slashing-unit class, instead of the v4 default of `0`:

| Parameter (env var) | Unit class | Rationale |
| --- | --- | --- |
| `SLASH_DUPLICATE_PROPOSAL_PENALTY` | `LARGE` | Equivocation on proposals breaks pipelined liveness. |
| `SLASH_DUPLICATE_ATTESTATION_PENALTY` | `LARGE` | Equivocation on attestations corrupts the consensus signal. |
| `SLASH_INVALID_CHECKPOINT_PROPOSAL_PENALTY` | `SMALL` | A bad checkpoint requires attesters to be disruptive; the proposer-side offense alone is sufficient first-stage enforcement. |

The following offenses MUST ship as defaults at `0` in the v5 client, deferring their activation to a subsequent AZIP and release:

| Parameter (env var) | Unit class | Reason |
| --- | --- | --- |
| `SLASH_ATTEST_INVALID_CHECKPOINT_PROPOSAL_PENALTY` | `0` (disabled) | Newly introduced by AZIP-7; re-execution-based attribution path not yet observed in production. |
| `SLASH_PROPOSE_DESCENDANT_OF_CHECKPOINT_WITH_INVALID_ATTESTATIONS_PENALTY` | `0` (disabled) | Newly introduced by AZIP-7; deferred to a subsequent release for the same reason. |
| `SLASH_DATA_WITHHOLDING_PENALTY` | `0` (disabled) | Carried forward from v4 deployment. Detection path changed materially in v5 (per-checkpoint mempool probe with `SLASH_DATA_WITHHOLDING_TOLERANCE_SLOTS` window); kept at zero through this release to gather tx-propagation telemetry before activation. |

### Updated L1 slashing-unit amounts

The L1 `SlashingProposer` contract reads three immutable amounts at construction. The v5 `SlashingProposer` MUST be deployed with:

| Constant | v4 deployment | v5 deployment |
| --- | --- | --- |
| `SLASH_AMOUNT_SMALL` | `2_000n` | `2_000n` (unchanged) |
| `SLASH_AMOUNT_MEDIUM` | `2_000n` | `5_000n` |
| `SLASH_AMOUNT_LARGE` | `2_000n` | `5_000n` |

The `localEjectionThreshold` parameter MUST remain unchanged at `190_000n` in the v5 deployment.

### Updated fee market parameter

The v5 `Rollup` MUST be deployed with:

| Parameter | v4 deployment | v5 deployment |
| --- | --- | --- |
| `provingCostPerMana` | `25_000_000` | `12_500_000` |

The value is fixed at deployment via the `Rollup` constructor's `GenesisRollupConfig` argument. 

### Other parameters

No other slashing or fee-market parameter is changed by this AZIP. In particular:

- `slashInactivityPenalty`, `slashBroadcastedInvalidBlockPenalty`, `slashDataWithholdingPenalty`, `slashProposeInvalidAttestationsPenalty`, `slashUnknownPenalty` remain at their v4 values.
- `slashOffenseExpirationRounds`, `slashGracePeriodL2Slots`, `slashExecuteRoundsLookBack`, `slashMaxPayloadSize` are unchanged at the protocol level.

## Rationale

### Why `LARGE` for both equivocation offenses

Equivocation is the most damaging slashable behavior currently detectable on the network, because it directly translates to multi-slot liveness loss under pipelining. Mapping both equivocation offenses to the same class (`LARGE`) preserves a simple economic story: equivocation is the worst thing a validator can do, and both forms of it are equally costly to attribute.

With an initial stake of `200_000n`, `SLASH_AMOUNT_LARGE = 5_000n`, and `localEjectionThreshold = 190_000n`, a validator's effective balance after `n` LARGE offenses is `200_000 - 5_000 · n`. Ejection occurs the first time that quantity drops strictly below `190_000`, which is at the third offense (185,000 < 190,000). A single isolated equivocation event therefore does not result in ejection, providing operational headroom for a one-off misconfiguration; a sustained pattern of three or more equivocations leads to removal from the validator set.

### Why `SMALL` for `BROADCASTED_INVALID_CHECKPOINT_PROPOSAL`

The author considered three positions:

1. **Disabled (`0`).** Symmetric with the other new offenses; conservative.
2. **`SMALL`.** Activated, but at the lowest tier.
3. **`MEDIUM`.**

Position 2 was chosen because (a) checkpoint proposals have been part of the protocol since the Alpha release and the validation logic is well-exercised, (b) the detection path for this specific offense is on the P2P side and does not require block re-execution, which limits both code complexity and false-positive surface, and (c) a single bad checkpoint proposal cannot itself harm the network without attestations following it, so a `SMALL` penalty is a calibrated first-stage response. 

### Why keep `SLASH_ATTEST_INVALID_CHECKPOINT_PROPOSAL_PENALTY` disabled

The attester-side companion offense was considered but rejected for activation in this AZIP. Two properties differentiate it from the proposer-side offense:

- **Blast radius.** A single triggering event slashes up to a full committee's worth of attesters, not a single proposer.
- **Detection mechanism.** Attribution relies on block re-execution and state-root comparison, which is a new enforcement path introduced in the v5 line.

The combination of large blast radius and a newer detection path argues for treating it like the other AZIP-7 offenses: keep the penalty at zero through one upgrade cycle, observe the proposer-side offense in production, then activate in a subsequent AZIP. This also matches the precedent set by v4, where every new offense ships at zero and is activated in a follow-up parameter update.

### Why not move `SMALL` along with `MEDIUM`/`LARGE`

Raising `SMALL` would also raise the effective penalty for every currently-active offense that is mapped to it, even though this AZIP does not propose to revise the harm-vs-penalty calibration for those offenses. Leaving `SMALL` at `2_000n` keeps the per-offense penalties for previously-active offenses constant, isolating the parameter change to the new and newly-activated offenses.

## Backwards Compatibility

This AZIP fixes deployment-time values for the v5 release; there is no in-band parameter update against the running v4 rollup. 

Operators that elect to remain on v4 software pointing at the v5 rollup are out of scope: the v4 client's slashing watchers would not be configured against the v5 defaults, and v4 validators would not vote for the activated offenses, putting them out of sync with the v5 majority. Operators MUST upgrade to v5 software in lockstep with the v5 rollup cutover.

Because both the L1 `SlashingProposer` (which holds `SLASH_AMOUNT_*` as immutables) and the L1 `Rollup` (which holds `provingCostPerMana` in compressed fee config) are fresh deployments under v5, no migration path or in-band parameter change is invoked. The v5 deployment is the activation.

## Test Cases

1. **Equivocation activation.** With `SLASH_DUPLICATE_PROPOSAL_PENALTY` set to `LARGE`, a proposer that signs two conflicting block proposals at the same slot results in a `DUPLICATE_PROPOSAL` offense recorded against that proposer with a vote weight matching `SLASH_AMOUNT_LARGE = 5_000n`.
2. **Attestation equivocation activation.** With `SLASH_DUPLICATE_ATTESTATION_PENALTY` set to `LARGE`, a validator that signs attestations over two different proposals at the same slot results in a `DUPLICATE_ATTESTATION` offense recorded against that validator with a vote weight matching `SLASH_AMOUNT_LARGE = 5_000n`.
3. **Invalid checkpoint proposal.** With `SLASH_INVALID_CHECKPOINT_PROPOSAL_PENALTY` set to `SMALL`, a proposer that broadcasts a structurally invalid checkpoint proposal over the P2P network is recorded with a `BROADCASTED_INVALID_CHECKPOINT_PROPOSAL` offense weighted at `SLASH_AMOUNT_SMALL = 2_000n`.
4. **Disabled offenses remain disabled.** With `SLASH_ATTEST_INVALID_CHECKPOINT_PROPOSAL_PENALTY` and `SLASH_PROPOSE_DESCENDANT_OF_CHECKPOINT_WITH_INVALID_ATTESTATIONS_PENALTY` set to `0`, the corresponding watchers run without emitting `WANT_TO_SLASH` events, and no votes are produced for those offense types.
5. **Ejection threshold preserved.** A validator accumulating offenses up to but not exceeding `localEjectionThreshold = 190_000n` MUST NOT be auto-ejected. A validator crossing that threshold MUST be ejected on the next eviction tick.
6. **Fee market.** After `provingCostPerMana` is set to `12_500_000`, base fees computed by the fee market for an identical block reflect the proportionally reduced proving subsidy.

## Economics Considerations

### Validator side

The effective marginal cost of equivocation rises from `0` to `5_000n` per offense (`SLASH_AMOUNT_LARGE`). The cost of a single invalid checkpoint proposal rises from `0` to `2_000n` (`SLASH_AMOUNT_SMALL`). For an honest, correctly configured node, none of these offenses is reachable under normal operation, so the expected slashing cost remains near zero.

Ejection occurs when a validator's effective balance falls strictly below `localEjectionThreshold = 190_000n`. Starting from a `200_000n` stake, a validator can absorb two LARGE-class slashes (effective balance `190_000n` after the second slash, which is not strictly below the threshold) and is ejected on the third. The corresponding figure for SMALL-class slashes is six (effective balance falls to `188_000n` after the sixth offense). This provides operational headroom for one or two episodes of misconfiguration before the validator is removed from the set.

### Prover side

Halving `provingCostPerMana` reduces the proving subsidy by 50% at constant mana spend. v5 proving compute is approximately 50% lower than v4, and L1 verification gas is 50% lower than v4. To first order, prover unit economics are preserved: the per-mana reward halves, and the per-mana cost halves. 

### Fee market

At constant mana consumption and constant L1 gas prices, lowering `provingCostPerMana` reduces the proving-subsidy component of the base fee. Users see a marginal reduction in fees on proving-bound flows. Sequencer revenue at constant gas is marginally higher.

## Security Considerations

### Increased blast radius for the equivocation offenses

A bug in either equivocation watcher could now produce real slashings rather than no-op offense records. The two watchers in scope are the AttestationPool-based P2P duplicate detector (longstanding) and the `CheckpointEquivocationWatcher` introduced for L1-vs-P2P equivocation. Both detection mechanisms are based on observing two signed messages by the same key for the same slot, which is unambiguous and not reachable by honest behavior. The risk of false positives is therefore low. Operators SHOULD nonetheless treat the first month after the v5 cutover as a monitoring period.

### Disabled offenses

Keeping `SLASH_ATTEST_INVALID_CHECKPOINT_PROPOSAL_PENALTY` and `SLASH_PROPOSE_DESCENDANT_OF_CHECKPOINT_WITH_INVALID_ATTESTATIONS_PENALTY` at zero means honest validators are not exposed to the false-positive risk inherent in re-execution-based attribution during this upgrade cycle. The trade-off is that proposers and committees that publish bad checkpoints downstream of an invalid attestation set face no direct economic consequence in this AZIP; the proposer-side `BROADCASTED_INVALID_CHECKPOINT_PROPOSAL` enforcement is the only checkpoint-content offense active under this AZIP.

Keeping `SLASH_DATA_WITHHOLDING_PENALTY` at zero means honest committees are not exposed to slashing during a p2p congestion event in which a node fails to gather all txs for a given checkpoint within the tolerance window, even though the committee did make the data available. The trade-off is that committees that genuinely withhold data face no direct economic consequence in this release. The watcher itself does not run when the penalty is zero (`server.ts` gates instantiation on `slashDataWithholdingPenalty > 0n`), so calibration data for the eventual activation MUST come from independent telemetry.

### Slashing unit asymmetry

Setting `SLASH_AMOUNT_MEDIUM = SLASH_AMOUNT_LARGE = 5_000n` collapses the distinction between the two upper tiers for any offense that distinguishes them. No active offense in this AZIP relies on that distinction, but future AZIPs that wish to use `MEDIUM` distinctly from `LARGE` would need to revisit the constants. The author considers this acceptable: the simpler two-tier structure (SMALL vs everything else) is preferable while the offense set is still being calibrated.

### Fee market

Reducing `provingCostPerMana` while leaving other fee-market parameters unchanged narrows the buffer between the subsidy and prover unit costs in a scenario where the realized v5 proving cost is higher than the modeled 50% reduction. Once the v5 rollup is deployed, the parameter remains adjustable in-place via the existing `Rollup.setProvingCostPerMana(EthValue)` governance call, providing a corrective path independent of any further rollup redeployment.

## Copyright Waiver

Copyright and related rights waived via [CC0](/LICENSE).
