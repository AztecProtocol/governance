# AZIP-31: Pluggable Sequencer Reward Calculator

## Preamble

| `azip` | `title` | `description` | `author` | `discussions-to` | `status` | `category` | `created` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 31 | Pluggable Sequencer Reward Calculator | Moves per-proposer sequencer reward policy out of the rollup into a governance-set calculator contract called once per epoch proof. | Zac Williamson <zac@aztec.foundation>, Santiago Palladino (@spalladino, santiago@aztec-labs.com) | https://github.com/AztecProtocol/governance/discussions/75 | Accepted | Core | 2026-10-01 |

## Abstract

Every proposer today earns the same sequencer share of the checkpoint reward. The rollup has no way to pay different proposers differently, and because reward computation is part of the rollup logic, any reward policy change requires a new rollup deployment. This AZIP adds a governance-set `sequencerRewardCalculator` address to the rollup. When an epoch proof pays out rewards, the rollup makes one batched, gas-bounded, read-only call to the calculator with the proposer of each newly proven checkpoint, the epoch, the default sequencer reward, and the checkpoint reward. The calculator returns one sequencer reward per checkpoint. The rollup validates the response shape and bounds each value by a protocol constant. Any failure or malformed response pays the default to every checkpoint. A zero calculator address pays the default unconditionally and is bit-identical to today's behavior. The prover share and transaction fees are untouched. The rollup itself carries no reward policy: which proposers earn more or less, and why, is entirely the calculator's concern.

## Background

- **Checkpoint reward.** The rollup pays a configured amount of AZTEC per proven checkpoint, drawn from the RewardDistributor. Governance sets the amount (`checkpointReward`) and the proposer's split (`sequencerBps`) through `setRewardConfig`. The **default sequencer reward** is `checkpointReward × sequencerBps / 10 000`. The **prover share** is the remainder.
- **Epoch proof.** Rewards are paid in `submitEpochRootProof`, once per proof that advances the proven tip. The proof carries the checkpoint headers. The rollup verifies the committee for the epoch and can derive the proposer of each checkpoint from the committee, the slot, and the epoch's sampling seed, without extra calldata.
- **Reward distribution.** For a proof that newly covers `n` checkpoints, the rollup claims `n × checkpointReward` from the RewardDistributor, or whatever smaller amount is available. It pays the proposers their split of what was actually claimed, evenly per checkpoint, and gives the prover pool the remainder. A shortfall therefore reduces both sides in proportion.
- **Defensive calls.** [AZIP-2](./azip-2.md) made the RewardDistributor and RewardBooster addresses immutable because a governance-set endpoint that reverts, return-bombs, or returns overflowing values could block proof submission. Any new governance-set endpoint on the proof path must be unable to do that.

## Impacted Stakeholders

**Sequencers.** Sequencer rewards per checkpoint become whatever the active calculator returns. With no calculator set, nothing changes. Operators predict revenue by calling the calculator's view with their attester.

**Provers.** The prover share is unchanged. The calculator call adds a bounded gas cost to `submitEpochRootProof`, paid by the submitting prover, with an upper bound fixed by protocol constants regardless of calculator complexity.

**Token holders and governance.** Governance gains one lever: the calculator address. Reward policy can change by deploying a new calculator and pointing the rollup at it, without a rollup upgrade. Governance is responsible for the calculator's correctness, including that it cannot be gamed into paying premiums it does not intend.

**Wallets, explorers and staking interfaces.** Reward estimation calls the calculator's view with the same arguments the rollup uses. There is no table to mirror.

## Motivation

The checkpoint reward is the protocol's instrument for paying validators. It has two global knobs, the amount and the split, that apply identically to every proposer. The protocol cannot express a reward policy that depends on who the proposer is, and changing that requires a new rollup deployment, because reward computation is part of the rollup logic.

There are reasons governance may want per-proposer policy. Stake is not homogeneous: tokens enter the validator set through different channels with different lock-up terms, liquidity, and cost basis. Governance may want to steer the reward budget towards stake that bears full market risk, pay a premium to attract a cohort into the validator set, or align rewards with the terms of a distribution program. These policies change over time as programs vest and new ones launch.

The obvious first step would be to build such a policy into the rollup: a table of overrides keyed by some classification of stake, resolved by querying the contracts that hold that stake. Every such table carries the rollup along with it. Each new classification means new contract interfaces in the rollup, each premium means authentication logic in the proof path, and each change to the entries or the rules means another rollup deployment.

The policy does not belong in the rollup. The rollup knows which attester proposed each checkpoint and what the default reward is. Everything else is policy, and policy should live in a contract governance can replace. This AZIP specifies that boundary and nothing else.

## Specification

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119 and RFC 8174.

### Calculator interface

```solidity
interface ISequencerRewardCalculator {
  /// @param epoch            The epoch whose checkpoints are being rewarded
  /// @param proposers        One attester address per newly proven checkpoint, in checkpoint order
  /// @param defaultReward    The default sequencer reward per checkpoint
  /// @param checkpointReward The total checkpoint reward (sequencer share plus prover share)
  /// @return rewards         One sequencer reward per entry of `proposers`, in the same order
  function getSequencerRewards(
    Epoch epoch,
    address[] calldata proposers,
    uint256 defaultReward,
    uint256 checkpointReward
  ) external view returns (uint256[] memory rewards);
}
```

The calculator learns the calling rollup from `msg.sender` and MAY read any rollup or GSE state it needs. It MUST be a view. The rollup passes one entry per checkpoint, including repeated proposers; deduplication, caching, and any lookups are the calculator's responsibility.

### Rollup configuration

- The rollup MUST store a `sequencerRewardCalculator` address in reward storage. The zero address means no calculator.
- The rollup MUST expose `setSequencerRewardCalculator(address)`, callable only by the rollup owner (Governance), following the same access pattern as `setRewardConfig`. There is no rate limit and no cooldown. The setter MUST emit an event with the previous and new addresses.
- The rollup MUST expose a view returning the current calculator address.
- The deployer MAY set an initial calculator at construction.

### Protocol constants

- `MAX_SEQUENCER_REWARD_PER_CHECKPOINT`: the largest sequencer reward the rollup accepts for one checkpoint. This is a validity bound for arithmetic safety, not an economic cap. It MUST be a protocol constant, and it MUST be large enough that no plausible policy reaches it. A suggested value is `1_000_000e18`, two thousand times the checkpoint reward at the time of writing.
- `CALCULATOR_GAS_BASE` and `CALCULATOR_GAS_PER_CHECKPOINT`: the gas stipend forwarded to the calculator is `CALCULATOR_GAS_BASE + CALCULATOR_GAS_PER_CHECKPOINT × n`, where `n` is the number of proposers passed. Both MUST be protocol constants. They SHOULD be set from the measured cost of the calculator governance intends to deploy first, with generous headroom, so that a policy of similar complexity never degrades. Suggested values are a base of `200_000` and `100_000` per checkpoint.

### Reward computation

For each accepted epoch proof that newly covers `n` checkpoints, the rollup MUST:

1. Derive the proposer of each newly covered checkpoint from the committee the proof already verifies, using the checkpoint's slot and the epoch's sampling seed. If the proof carries no committee (escape-hatch epochs, or a target committee size of zero), the rollup MUST skip the calculator and pay the default for every checkpoint.
2. If `sequencerRewardCalculator` is the zero address, pay the default for every checkpoint.
3. Otherwise, call `getSequencerRewards(epoch, proposers, defaultReward, checkpointReward)` via `staticcall` with exactly the stipend above.
4. Accept the response only if it is well formed: the call succeeded, the return data has exactly the expected size and shape for `n` entries, and every value is at most `MAX_SEQUENCER_REWARD_PER_CHECKPOINT`. See Security Considerations for the exact checks and why they matter.
5. If the response is accepted, checkpoint `i` receives `rewards[i]`. Otherwise every checkpoint receives the default.

A failed or malformed calculator call MUST NOT revert proof submission under any circumstances.

### Distribution

- The prover reward per checkpoint remains `checkpointReward − defaultReward` and MUST NOT depend on the calculator.
- The desired draw is `n × (checkpointReward − defaultReward) + Σ rewards[i]`. It is bounded above by `n × (checkpointReward + MAX_SEQUENCER_REWARD_PER_CHECKPOINT)`.
- The rollup MUST claim only the desired draw from the RewardDistributor. Amounts not paid because a reward is below the default remain in the distributor.
- Shortfall handling keeps today's proportional outcome: if the distributor holds less than the desired draw, each checkpoint's sequencer reward is scaled by `available / desired` and the prover pool receives the remainder.
- Per-checkpoint sequencer rewards are credited to the coinbase as today, together with the sequencer fee share. Transaction fees, the protocol fee, and the prover fee are unchanged.

### Scope of rollup changes

The rollup MUST NOT read the GSE, token position contracts, or any other external state on the reward path beyond the single calculator call. It carries no per-proposer reward state.

### Deployment

Reward computation is part of the rollup logic, so this change requires a new rollup deployment through a governance proposal. A rollup deployed with a zero calculator pays rewards identically to a rollup without this feature.

V6 MUST initially deploy with `sequencerRewardCalculator` set to the zero address, preserving the default sequencer reward for all proposers. Any subsequent policy that reduces or increases rewards for particular proposers MUST be specified in a separate AZIP and activated through the AZUP governance process. This AZIP does not activate reduced insider rewards or boosted rewards.

### Client mirrors

Node software that predicts validator rewards MUST call the calculator's view with the same arguments the rollup would pass, and MUST apply the same fallback when the calculator is unset or the response is invalid.

## Rationale

**Why a calculator rather than a table in the rollup.** A table in the rollup ties every policy to the rollup's lifecycle: its size, the interfaces it needs to classify proposers, and any authentication those interfaces require all become rollup code, and none of it can change without a new deployment. Moving the policy behind one call keeps the rollup's reward path to a single, fixed shape.

**Why one batched call.** A per-proposer call would multiply external calls by up to 32 per proof. Passing the whole proof's proposers at once costs one call, and lets the calculator deduplicate and cache in memory exactly as the rollup does now.

**Why the rollup passes one proposer per checkpoint rather than distinct proposers.** Deduplication exists only to save gas on repeated lookups, and the lookups now live in the calculator. Keeping the rollup side per-checkpoint avoids any per-proposer cache in the rollup and the committee-size constraints such a cache would impose, keeps the proposers-to-rewards mapping trivial, and lets a future policy be checkpoint-dependent without an interface change.

**Why the rollup does not pass withdrawers.** The rollup no longer needs them for anything, and the calculator can read the GSE once per distinct proposer after it deduplicates. Not passing them keeps the rollup's reward path free of GSE reads.

**Why `checkpointReward` is passed even though the calculator could read it.** It costs one word and lets a policy express rewards relative to the total without a call back into the rollup.

**Why a validity bound and not an economic cap.** AZIP-2 identifies an endpoint returning `type(uint256).max` as a way to overflow the rollup's accounting and revert the proof. The bound closes that. It is deliberately far above any plausible reward so that it never constrains policy, including premiums above the default. Economic bounds are governance's job, and governance already controls the checkpoint reward itself without any cap or rate limit.

**Why failure pays defaults rather than reverting.** This is the AZIP-2 principle: no governance-set endpoint may block proof submission. Paying defaults is the one outcome governance could already produce through `setRewardConfig`, so a broken or hostile calculator gains no power over the protocol.

**Why no rate limit on the setter.** Rate limits exist where a parameter can impair a user guarantee: `provingCostPerMana` gates the escape hatch, the protocol margin of [AZIP-23](./azip-23.md) is paid by users. Sequencer rewards affect operator revenue, not user safety, and `setRewardConfig` already changes them with no limit. The governance proposal delay gives operators notice.

**Why `MAX_SEQUENCER_REWARD_PER_CHECKPOINT` is a constant.** A governance parameter would be one more thing to set and reason about, for a bound whose only purpose is to keep sums from overflowing. A constant with a large margin does the job.

### Alternatives considered

- **Governance-updateable override table in the rollup, with per-entry eligibility checkers.** Keeps policy state in the rollup and still bakes the registry resolution into it. Each new kind of policy needs a rollup change. Rejected in favor of externalizing the whole computation.
- **Per-proposer calculator calls with rollup-side deduplication.** More calls, and a dedup cache in the rollup adds state and constraints the calculator can carry instead. Rejected.
- **Calculator returns a boolean eligibility flag with amounts kept in the rollup.** Keeps amounts readable from rollup state, but still requires a table in the rollup and cannot express per-checkpoint or multi-tier policies. Rejected.
- **Immutable calculator address, as for the distributor and booster.** Would require a redeploy per policy change, which is the problem this AZIP solves. The defensive call makes mutability safe. Rejected.

## Backwards Compatibility

This change requires a new rollup deployment. With a zero calculator, reward distribution is identical to a rollup without this feature. Fee distribution, prover rewards, and the booster are unchanged.

## Test Cases

- A zero calculator pays every checkpoint the default, byte-for-byte identical to the current path.
- A calculator returning the default for every entry produces the same distribution as a zero calculator.
- A calculator returning values below, equal to, and above the default pays exactly those values, and values above the default are paid in full with no clamp below `MAX_SEQUENCER_REWARD_PER_CHECKPOINT`.
- A calculator that reverts, burns all gas, returns too little data, too much data, a wrong offset, a wrong length, or any value above `MAX_SEQUENCER_REWARD_PER_CHECKPOINT`: every checkpoint receives the default and proof submission succeeds.
- Returned data larger than the expected size is not copied; a return-bombing calculator cannot raise the caller's gas beyond the stipend plus the fixed copy.
- Repeated proposers within a proof are passed once per checkpoint and receive the per-checkpoint value the calculator returned.
- Escape-hatch epochs and zero-size committees skip the calculator and pay the default.
- A distributor shortfall scales sequencer rewards proportionally and gives the remainder to the prover pool.
- The setter rejects non-owner callers, accepts the zero address, and emits the event.
- Gas: proof submission cost with a representative calculator is measured for 1, 8, 16, and 32 checkpoints, and the worst case fits within the stipend.

## Economics Considerations

With a zero calculator there is no economic change. With a calculator, the sequencer reward per checkpoint is whatever the policy returns, bounded only by `MAX_SEQUENCER_REWARD_PER_CHECKPOINT`. The prover share is fixed by configuration. The per-checkpoint draw from the RewardDistributor therefore lies between the prover share alone, when the policy pays zero, and the prover share plus the bound. Rewards below the default slow the growth of circulating supply by the difference, per affected checkpoint. Rewards above the default raise it. Each policy's economic analysis belongs with that policy, not with this AZIP.

Rewards change operator income without changing duties or slashing exposure. Validators whose economics no longer justify operation exit through the ordinary withdrawal path, subject to its delays, which governance should account for when adopting a policy that reduces rewards.

## Security Considerations

- **Hostile or broken calculator.** The calculator is a governance-set endpoint on the proof path, which AZIP-2 identifies as a liveness risk: an endpoint that reverts, burns gas, returns oversized data, or returns overflowing values must not be able to block `submitEpochRootProof`. The rollup therefore MUST call it as follows. The call is a `staticcall` with exactly the stipend from the protocol constants, so the calculator cannot change state and cannot consume more than a bounded amount of gas. After the call, the rollup MUST read `returndatasize` and accept the response only if it is exactly `64 + 32 × n` bytes; it MUST NOT copy any return data before that check, and MUST NOT copy more than that size. The stipend bounds what the calculator can spend but not what it can return, and the caller pays for every byte it copies, in copy cost and in memory expansion; a rollup that copied the whole response, or used a high-level call that decodes it, could be forced out of gas by the response alone and would fail the proof instead of falling back. The rollup then MUST verify that the ABI head encodes an offset of `32` and a length of `n`, and that every value is at most `MAX_SEQUENCER_REWARD_PER_CHECKPOINT`, so that summing up to 32 of them cannot overflow the accounting. Any failed check pays the default to every checkpoint and never reverts.
- **Governance power.** Setting the calculator cannot do anything governance could not already do with `setRewardConfig`, except express the same budget unevenly across proposers. A calculator paying everyone zero is equivalent to `sequencerBps = 0`. Neither affects user exits or fee pricing.
- **Policy correctness lives in the calculator.** The rollup does not authenticate anything about a proposer. A calculator that pays premiums based on data the proposer controls, such as a withdrawer's self-reported answers, can be gamed. The required discipline is to pay premiums only on facts attested by contracts the proposer cannot forge. Calculator audits are a governance prerequisite for any premium-paying policy.
- **Gas on provers.** The calculator's cost falls on whoever submits the proof, including partial epoch proofs. The stipend bounds it. A policy that exceeds the stipend silently pays defaults, which is a liveness-preserving failure but a confusing one; calculators SHOULD be benchmarked against the constants before adoption.
- **State at proof time.** Rewards reflect calculator state, and whatever state the calculator reads, when the proof lands, not when the checkpoint was proposed. This is acceptable for reward policy, but calculators that want epoch-accurate answers must keep their own history.
- **Shortfall interaction.** A policy paying large premiums can drain the distributor faster. The proportional scaling degrades gracefully, but governance should size distributor funding to the policy.

## Copyright Waiver

Copyright and related rights waived via [CC0](/LICENSE).

