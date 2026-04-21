# AZIP-2: Rollup Hardening Against Governance Misconfiguration

## Preamble

| `azip` | `title`                                              | `description`                                                                                           | `author`    | `discussions-to`                                          | `status` | `category` | `created`  |
| ------ | ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------- | ----------- | --------------------------------------------------------- | -------- | ---------- | ---------- |
| 2      | Rollup Hardening Against Governance Misconfiguration | Bakes timelocks, rate limits, and resilience into the rollup so governance cannot mute the escape hatch | @just-mitch | https://github.com/AztecProtocol/governance/discussions/2 | Draft    | Core       | 2026-03-31 |

## Abstract

This proposal hardens the rollup against governance actions that could halt finalization, price transactions out of inclusion, or revoke the user exit guarantee, by enforcing the constraints directly in the rollup contract. The escape hatch can only be set once, and is immutable thereafter. Critical-path calls into the `RewardDistributor` and `RewardBooster` are gas-capped and wrapped in `try/catch`. `setProvingCostPerMana` is gated by a 30-day cooldown, a symmetric 3/2 multiplicative step, and a floor of 2. `updateStakingQueueConfig` is validated on every call to keep flush sizes positive. `setSlasher` is replaced by a 60-day queue/finalize flow, and `setLocalEjectionThreshold` is removed.

## Impacted Stakeholders

- **Sequencers** — The slasher can no longer be swapped instantly; validators who object to a queued slasher have time to exit. The ejection floor cannot be raised out from under them. The flush-size invariants keep the queue admitting new sequencers.
- **Provers** — A broken or malicious `RewardDistributor` / `RewardBooster` can no longer block `submitEpochRootProof`; failures surface as events and epochs still finalize. `provingCostPerMana` cannot move to extreme values instantly.
- **Tokenholders** — Retain full upgrade authority, but lose the ability to issue a single transaction that bricks the rollup or revokes the exit guarantee.
- **App Developers** — Get a stable, for-life exit guarantee once the escape hatch is set, and a fee model that cannot be priced out of existence in a single vote.
- **Infrastructure Providers** — Reward-endpoint failures surface as `CheckpointClaimFailed` / `BoosterUpdateFailed` events instead of transaction reverts. Slasher changes are announced 60 days in advance via `PendingSlasherQueued`.

## Motivation

### Current Limitations

A single approved Governance proposal on today's rollup can:

- `updateEscapeHatch(ADDRESS)` — delete the exit guarantee outright.
- `setRewardConfig(booster, rewardDistributor, ...)` — point at a reverting endpoint, blocking `submitEpochRootProof`.
- `setProvingCostPerMana(uint.max)` — price the fee model out of usability.
- `updateStakingQueueConfig(normalFlushSizeMin=0, …)` — close the validator queue.
- `setSlasher()` / `setLocalEjectionThreshold()` — eject arbitrary validators.

To give users a guarantee that they have at least a 30 day window to exit at any time via the escape hatch, the first 3 issues must be rectified. Constraining the other two afford meaningful practical assurances to users and node operators.

A "stage-2" rollup could almost certainly be achieved by putting a ~60 day timelock in front of all of these operations, but that would be suboptimal: it is conceivable that Governance might honestly want to update the RewardDistributor or provingCostPerMana with little delay. Therefore, we address each of these items in turn.

## Specification

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119 and RFC 8174.

### Escape Hatch Immutability (One-shot Set)

`updateEscapeHatch(address)` SHALL be renamed `setEscapeHatch(address)` and made "one-shot":

- MUST revert with `ValidatorSelection__EscapeHatchCannotBeZero` if called with the zero address.
- MUST revert with `ValidatorSelection__EscapeHatchAlreadySet` if an escape hatch was previously registered.
- SHALL write the address into `escapeHatchCheckpoints` keyed to the start of the next epoch, so the registration never retroactively affects the current epoch.
- No path — owner-gated, governance-gated, or otherwise — MAY remove, replace, or modify the address after it is set. A rollup that wants no escape hatch simply never calls `setEscapeHatch`.

The `EscapeHatchUpdated` event SHALL be renamed `EscapeHatchSet`.

### Reward Endpoint Resilience (try/catch)

All external calls from `RewardLib.handleRewardsAndFees` into the `RewardDistributor` and `RewardBooster` MUST be gas-capped and wrapped in `try/catch`:

1. `distributor.canonicalRollup()` — `CANONICAL_ROLLUP_GAS = 25_000`. On revert, emit `CheckpointClaimFailed(distributor, requested)` and treat the epoch as having zero claimable checkpoint rewards.
2. `distributor.claim(address(this), amount)` — `CLAIM_GAS = 50_000`. Same failure handling as (1).
3. `booster.updateAndGetShares(prover)` — `BOOSTER_UPDATE_GAS = 45_000`. On revert, emit `BoosterUpdateFailed(prover)` and credit the prover with `FALLBACK_BOOSTER_SHARES = 1`. The sentinel MUST be non-zero so that during a booster outage every submitter still receives an equal fraction of the epoch's rewards; a zero fallback would drive `summedShares` to 0 and trip the `shares > 0` short-circuit in `claimProverRewards`, zeroing out prover rewards for an epoch that otherwise finalized. It MUST be minimal so a failing booster cannot materially inflate a prover's reward share. Preserving the `$sr.shares[prover] == 0` duplicate-submission guard is a side benefit.

Note: the gas caps are sized against honest-path cold-call measurements to those functions as they exist today with ~1.5x headroom.

### `provingCostPerMana` Rate Limit

`setProvingCostPerMana(uint256 v)` MUST enforce:

1. **Floor**: `v >= MIN_PROVING_COST_PER_MANA = 2`. Values below 2 degenerate the step-ratio algebra. `FeeLib.initialize` MUST enforce the same floor.
2. **Cooldown**: revert if `block.timestamp < provingCostLastUpdate + PROVING_COST_UPDATE_INTERVAL` (30 days). Waived when `provingCostLastUpdate == 0` so the first post-init update can land.
3. **Symmetric multiplicative step**: revert unless `v * 2 <= current * 3 && v * 3 >= current * 2` (i.e. 3/2 in either direction).

Combined, this caps cumulative change at ~10× over ~170 days and ~100× over ~340 days. The `FeeStore` struct gains `uint64 provingCostLastUpdate`. New errors: `FeeLib__ProvingCostBelowFloor`, `FeeLib__ProvingCostCooldown`, `FeeLib__ProvingCostStepExceeded`.

### Staking Queue Flush-Size Invariants

The checks `normalFlushSizeMin > 0` and `normalFlushSizeQuotient > 0` SHALL move into `StakingLib.assertValidQueueConfig(StakingQueueConfig)` and be called from both `RollupCore`'s constructor and `StakingLib.updateStakingQueueConfig`. This prevents governance from ever closing the queue (`normalFlushSizeMin = 0`) or causing division by zero in `getEntryQueueFlushSize`.

### Slasher 60-Day Queue/Finalize Flow

`setSlasher(address)` SHALL be replaced with:

- `queueSetSlasher(address _slasher)` — owner-gated. Sets `pendingSlasher` and `pendingSlasherReadyAt = block.timestamp + SLASHER_EXECUTION_DELAY` (60 days). Overwrites any existing pending value and resets the timer. Emits `PendingSlasherQueued`.
- `cancelSetSlasher()` — owner-gated. Clears the pending slasher or reverts with `Staking__NoPendingSlasher`. Emits `PendingSlasherCancelled`.
- `finalizeSetSlasher()` — **permissionless**. Reverts with `Staking__NoPendingSlasher` or `Staking__SlasherNotReady(readyAt)`. On success, applies the change and emits `SlasherUpdated`.

The delay is permissionless so that Governance doesn't need to be relied on to effect the queued change.

`IStakingCore` loses `setSlasher` and the `LocalEjectionThresholdUpdated` event, and gains the three new selectors plus `PendingSlasherQueued` / `PendingSlasherCancelled`. `IStaking` gains `getPendingSlasher()` and `getSlasherExecutionDelay()` readers.

### `setLocalEjectionThreshold` Removal

`setLocalEjectionThreshold(uint256)` SHALL be removed from `RollupCore`, `IStakingCore`, `ValidatorOperationsExtLib`, and `StakingLib`. `localEjectionThreshold` remains on `StakingStorage` (set in `StakingLib.initialize`) and readable via `getLocalEjectionThreshold()`; there is no post-deployment mutation path. A rollup that needs a different threshold must be redeployed. This eliminates the "raise the threshold to retroactively arm ejections" attack surface entirely.

### Functions Deliberately Unchanged

`setRewardConfig`, `updateManaTarget`, `updateStakingQueueConfig` (beyond flush-size invariants), and `transferOwnership` retain their existing owner-gated semantics. Their worst-case outcomes no longer mute the escape hatch:

- `setRewardConfig` rotations to a reverting endpoint are absorbed by the `try/catch` above.
- `updateManaTarget` is up-only and unbounded, but raising it only drives per-block cost toward `provingCostPerMana × manaUsed` — which is already rate-limited — and does not block L2→L1 messaging.
- `updateStakingQueueConfig` must keep `normalFlushSizeMin > 0` and `normalFlushSizeQuotient > 0`.

### No Change to Voting Mechanics

Voting thresholds, quorum requirements, and governance approval flow are unchanged.

## Rationale

### Why Full Escape Hatch Immutability

Any governance control over the escape hatch — even restricted to "can only lower the bond" — introduces a DOS vector: too-low a bond makes escape-hatch slots trivially sybillable exactly when they matter most. Full immutability eliminates this and matches the Stages Framework convention that an escape hatch "owes to its name" to be immutable.

### What Governance Can Still Do

After this proposal, malicious governance's residual surface is:

- Raise `provingCostPerMana` gradually, bounded by the 3/2 step per 30 days — always slower than the exit guarantee.
- Raise `manaTarget` (bounded in effect by the proving-cost rate limit — cannot mute the hatch).
- Rotate the reward distributor/booster to a reverting endpoint (absorbed by `try/catch`).
- Queue a slasher change (applies only after 60 days, longer than the ~38-day validator withdrawal window).
- Adjust the share of rewards that go to sequencers versus provers such that it is not economical for one of those actors to participate.
- Adjust the checkpoint reward to the same effect.

No residual action mutes the escape hatch.

### Why a Cooldown + Step Instead of a Rolling Window

A rolling window bounds cumulative change by re-anchoring to the value at window start; a cooldown-plus-step bounds it by a per-update ratio plus a minimum inter-update delay. For a single parameter, the latter is simpler (one timestamp of state, one revert path) and harder to get wrong than window-position/step interactions.

## Backwards Compatibility

1. **ABI**: `setSlasher` → `queueSetSlasher` / `cancelSetSlasher` / `finalizeSetSlasher`. `setLocalEjectionThreshold` removed. `updateEscapeHatch` → `setEscapeHatch`. `EscapeHatchUpdated` → `EscapeHatchSet`. `LocalEjectionThresholdUpdated` removed. New events `PendingSlasherQueued`, `PendingSlasherCancelled`.
2. **Timing**: Slasher replacements take effect 60 days after queueing.
3. **Parameter constraints**: `setProvingCostPerMana` reverts on cooldown violation, step violation, or `v < 2`. `updateStakingQueueConfig` reverts on zero flush fields (matching the existing constructor invariant).
4. **Escape hatch finality**: `setEscapeHatch` is final for the life of the rollup; deployers must verify the address before calling.

## Test Cases

1. **Escape hatch one-shot**: `setEscapeHatch(nonZero)` succeeds once; second call reverts with `EscapeHatchAlreadySet`; zero-address call reverts with `EscapeHatchCannotBeZero`.
2. **Reward distributor / booster revert tolerance**: A reverting `canonicalRollup`, `claim`, or `updateAndGetShares` MUST NOT cause `submitEpochRootProof` to revert; the appropriate event fires and the fallback value is used.
3. **Gas-cap isolation**: An endpoint that burns unbounded gas MUST be cut off at the cap without consuming the proof submitter's remaining budget.
4. **Proving cost floor / step / cooldown**: `setProvingCostPerMana(0|1)` reverts with `ProvingCostBelowFloor`; from 1000, setting 1501 or 666 reverts with `ProvingCostStepExceeded`, while 1500 / 667 succeed; the first post-init update lands immediately, a second within 30 days reverts with `ProvingCostCooldown`.
5. **Flush-size invariants on update**: `updateStakingQueueConfig` with zero `normalFlushSizeMin` or `normalFlushSizeQuotient` reverts.
6. **Slasher queue flow**: `queueSetSlasher` / `cancelSetSlasher` are owner-only; `finalizeSetSlasher` is permissionless, reverts before 60 days with `SlasherNotReady`, and applies the change after. Queue overwrite resets the timer; cancel without a pending queue reverts with `NoPendingSlasher`.
7. **`setLocalEjectionThreshold` removed**: selector is not reachable on the deployed rollup.

## Security Considerations

### Reward Call Resilience vs Correctness

Wrapping reward-endpoint calls in `try/catch` trades per-epoch reward correctness for system liveness. Fallbacks are conservative (zero checkpoint reward, one booster share) so provers are never over-credited. Operators MUST treat `CheckpointClaimFailed` / `BoosterUpdateFailed` as signals to rotate the endpoint; the rollup does not self-heal. Gas caps (25k / 50k / 45k) must remain conservatively above honest-path cold-call cost — under-sized caps brick the honest path, over-sized caps let a malicious endpoint consume the rest of the transaction's gas.

### Rate Limit and Queue Bypass

The cooldown check anchors on `provingCostLastUpdate`, so multicalls and repeated proposals within a window MUST revert. The step bound is symmetric so governance cannot deflate proving cost to the floor in one step either. The slasher queue resets its timer on overwrite, so governance cannot accrue "credit" from a cancelled queue.

### Escape Hatch Finality

The one-shot `setEscapeHatch` is load-bearing for the exit guarantee and cannot be reversed. A misconfigured first call is unrecoverable — deployers MUST verify the address and implementation before calling.

### Future Rollup Versions

New rollups deployed via `Registry.addRollup()` MUST carry the same or stricter versions of these constraints. Relaxing any of them on a future rollup would weaken the exit guarantee for its users.

## Copyright Waiver

Copyright and related rights waived via [CC0](/LICENSE).
