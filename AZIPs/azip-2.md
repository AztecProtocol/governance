# AZIP-2: Rollup Hardening Against Governance Misconfiguration

## Preamble

| `azip` | `title`                                              | `description`                                                                                             | `author`    | `discussions-to`                                          | `status` | `category` | `created`  |
| ------ | ---------------------------------------------------- | --------------------------------------------------------------------------------------------------------- | ----------- | --------------------------------------------------------- | -------- | ---------- | ---------- |
| 2      | Rollup Hardening Against Governance Misconfiguration | Bakes timelocks, rate limits, and immutability into the rollup so governance cannot mute the escape hatch | @just-mitch | https://github.com/AztecProtocol/governance/discussions/2 | Accepted    | Core       | 2026-03-31 |

## Abstract

This proposal hardens the rollup against governance actions that could halt finalization, price transactions out of inclusion, or revoke the user exit guarantee, by enforcing the constraints directly in the rollup contract. The escape hatch can only be set once, and is immutable thereafter. The `RewardDistributor` and `RewardBooster` addresses are likewise immutable post-deployment, and the `RewardDistributor` has been generalized to support hold funds earmarked for arbitrary addresses (e.g. old rollups). `setProvingCostPerMana` is rate-limited by a 30-day cooldown and a bounded per-update step. `updateStakingQueueConfig` is validated on every call to keep flush sizes positive. `setSlasher` is replaced by a 60-day queue/finalize flow, and `setLocalEjectionThreshold` is removed.

## Impacted Stakeholders

- **Sequencers** — The slasher can no longer be swapped instantly; validators who object to a queued slasher have time to exit. The ejection floor cannot be raised out from under them. The flush-size invariants keep the queue admitting new sequencers.
- **Provers** — The `RewardDistributor` and `RewardBooster` addresses are fixed for the life of the rollup, so governance cannot rotate them to endpoints that block, starve, or corrupt `submitEpochRootProof`. Provers on a rollup that is no longer canonical can still be rewarded via subsidies held in the `RewardDistributor`. `provingCostPerMana` cannot move to extreme values instantly.
- **Tokenholders** — Retain full upgrade authority, but lose the ability to issue a single transaction that bricks the rollup or revokes the exit guarantee.
- **App Developers** — Get a stable, for-life exit guarantee once the escape hatch is set, and a fee model that cannot be priced out of existence in a single vote.
- **Infrastructure Providers** — Reward-endpoint addresses are fixed at deployment and cannot be rotated by governance. Slasher changes are announced 60 days in advance via `PendingSlasherQueued`. Some ABI changes on new contracts.

## Motivation

### Current Limitations

A single approved Governance proposal on today's rollup can:

- `updateEscapeHatch(ADDRESS)` — delete the exit guarantee outright.
- `setRewardConfig(booster, rewardDistributor, ...)` — point at an adversarial endpoint that reverts, returns overflowing values, return-bombs, or re-enters; any of these block `submitEpochRootProof`.
- `setProvingCostPerMana(uint.max)` — price the fee model out of usability.
- `updateStakingQueueConfig(normalFlushSizeMin=0, …)` — close the validator queue.
- `setSlasher()` / `setLocalEjectionThreshold()` — eject arbitrary validators.

To give users a guarantee that they have at least a 30 day window to exit at any time via the escape hatch, the first 3 issues must be rectified. Constraining the other two afford meaningful practical assurances to users and node operators.

A "stage-2" rollup could almost certainly be achieved by putting a ~60 day timelock in front of all of these operations, but that would be suboptimal: it is conceivable that Governance might honestly want to update `provingCostPerMana` with little delay, and the reward-endpoint addresses do not need to be mutable at all once the `RewardDistributor` itself supports subsidizing non-canonical rollups. Therefore, we address each of these items in turn.

## Specification

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119 and RFC 8174.

### Escape Hatch Immutability (One-shot Set)

`updateEscapeHatch(address)` SHALL be renamed `setEscapeHatch(address)` and made "one-shot":

- MUST revert with `ValidatorSelection__EscapeHatchCannotBeZero` if called with the zero address.
- MUST revert with `ValidatorSelection__EscapeHatchAlreadySet` if an escape hatch was previously registered.
- SHALL write the address into `escapeHatchCheckpoints` keyed to the start of the next epoch, so the registration never retroactively affects the current epoch.
- No path — owner-gated, governance-gated, or otherwise — MAY remove, replace, or modify the address after it is set. A rollup that wants no escape hatch simply never calls `setEscapeHatch`.

The `EscapeHatchUpdated` event SHALL be renamed `EscapeHatchSet`.

### Reward Distributor and Booster Immutability

The `rewardDistributor` and `rewardBooster` address fields of `RollupStore.config` MUST be set once — in the constructor or `initialize` — and MUST NOT be mutable post-deployment. `setRewardConfig` SHALL be modified to no longer accept or write these two addresses; the remaining reward parameters (sequencer/prover split, checkpoint reward, etc.) retain their existing owner-gated semantics. Rotating either address requires redeploying the rollup via `Registry.addRollup`.

### Per-Address Subsidy Path

`IRewardDistributor` exposes:

- `availableTo(address recipient) external view returns (uint256)` — when `recipient == canonicalRollup()`, returns `ASSET.balanceOf(distributor) - totalEarmarkedBalance + specificRecipientBalance[recipient]`. Otherwise returns `specificRecipientBalance[recipient]`. The canonical rollup is the only address with access to the implicit (un-earmarked) pool; everyone else sees only their earmarked balance.
- `subsidizeAddress(address recipient, uint256 amount) external` — permissionless. Reverts with `RewardDistributor__ZeroRollup` if `recipient == address(0)`. Pulls amount of `ASSET` from the caller and increments both `specificRecipientBalance[recipient]` and `totalEarmarkedBalance` by amount. No validation is performed that recipient is a registered rollup, or a rollup at all — any address can be earmarked.

`RewardDistributor.claim(address to, uint256 amount)` authorizes the caller implicitly through balance accounting in the internal `_transfer(msg.sender, to, amount)`:
- When `msg.sender == canonicalRollup()`, the implicit pool (balanceOf - totalEarmarkedBalance) is consumed first; any shortfall is drawn from `specificRecipientBalance[msg.sender]`.
- For any other caller, only `specificRecipientBalance[msg.sender]` is available.
- Insufficient funds revert with `RewardDistributor__InsufficientAvailable(requested, available)`. When earmarked funds are consumed, both `specificRecipientBalance[msg.sender]` and totalEarmarkedBalance are decremented by the amount drawn from the earmarked bucket.

`recoverFrom(address from, address to, uint256 amount)` is governance-only (registry owner) and shares the same `_transfer` accounting path as `claim`, with `from` substituted for `msg.sender`. Because `totalEarmarkedBalance` is decremented in lockstep with `specificRecipientBalance[from]`, governance recovery cannot drive `availableTo(canonicalRollup())` negative: the implicit-pool component (balanceOf - totalEarmarkedBalance) is invariant under earmarked draws, and direct-pool draws against the canonical address are bounded by the contract's ASSET balance.

The pre-existing `recover(address,address,uint256)` ABI shape was renamed to `recoverFrom` to avoid a 4-byte selector collision with the previous `recover(_asset,_to,_amount)`. Wrong-asset recovery moves to `recoverWrongAsset(address asset, address to, uint256 amount)`, which is also governance-only and reverts with `RewardDistributor__WrongRecoverMechanism` if `asset == ASSET`.

`RewardLib.handleRewardsAndFees` reads `distributor.availableTo(address(this))` and clamps `amountToClaim` to that value before calling `distributor.claim(address(this), amountToClaim)`.

Any funds transferred to the `RewardDistributor` without invoking subsidizeAddress accrue to the canonical rollup via `balanceOf - totalEarmarkedBalance`, preserving the "mint/airdrop into the distributor" funding path.

### Legacy Reward Distributor Handover

The currently deployed `RewardDistributor` at `0x3D6A1B00C830C5f278FC5dFb3f6Ff0b74Db6dfe0` holds the active reward pool for the canonical rollup. When v5 is deployed with the new immutable `RewardDistributor`, the v4 rollup ceases to be canonical under the Registry, so its `claim(address(this), …)` path on the legacy distributor stops authorizing (the legacy `msg.sender == canonicalRollup()` check fails). The reward pool therefore MUST be moved to the new distributor in the same governance action that promotes v5.

Concretely, the `Registry.addRollup(v5)` governance proposal MUST be bundled with a call to `legacyDistributor.recover(ASSET, newDistributor, legacyDistributor.ASSET.balanceOf(legacyDistributor))`, transferring the full reward-asset balance.

Funds landing in the new distributor via this transfer are untagged and therefore accrue to the new canonical (v5).

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

`setRewardConfig` (for the non-address reward parameters), `updateManaTarget`, `updateStakingQueueConfig` (beyond flush-size invariants), and `transferOwnership` retain their existing owner-gated semantics. Their worst-case outcomes no longer mute the escape hatch:

- `updateManaTarget` is up-only and unbounded, but raising it only drives per-block cost toward `provingCostPerMana × manaUsed` — which is already rate-limited — and does not block L2→L1 messaging.
- `updateStakingQueueConfig` must keep `normalFlushSizeMin > 0` and `normalFlushSizeQuotient > 0`.

### No Change to Voting Mechanics

Voting thresholds, quorum requirements, and governance approval flow are unchanged.

## Rationale

### Why Full Escape Hatch Immutability

Any governance control over the escape hatch — even restricted to "can only lower the bond" — introduces a DOS vector: too-low a bond makes escape-hatch slots trivially sybillable exactly when they matter most. Full immutability eliminates this and matches the Stages Framework convention that an escape hatch "owes to its name" to be immutable.

### Why Immutable Reward Endpoints Over try/catch

An earlier draft wrapped every `RewardDistributor` / `RewardBooster` call in `try/catch` with a gas cap. That approach only defends against reverts at the call boundary. It does not defend against:

- An endpoint returning valid but adversarial values (e.g. `type(uint256).max` from `updateAndGetShares`) that overflow the rollup's own accounting and revert the outer transaction after `try/catch` has already succeeded.
- Return-bomb attacks that burn gas copying oversized return-data into the caller's memory.
- Future gas repricings that invalidate hand-tuned gas caps and either brick the honest path (cap too low) or let a malicious endpoint consume the submitter's remaining gas (cap too high).
- Re-entrancy or state-mutation side effects that `try/catch` does not restrain.

Fixing the addresses at deployment retires the entire class. The only legitimate use case for mutability — keeping an old rollup's provers and sequencers rewarded after a new canonical is promoted — is served by the per-address subsidy path on the distributor itself, which requires no governance action (`subsidizeAddress` is permissionless).

### What Governance Can Still Do

After this proposal, malicious governance's residual surface is:

- Raise `provingCostPerMana` gradually, bounded by the 3/2 step per 30 days — always slower than the exit guarantee.
- Raise `manaTarget` (bounded in effect by the proving-cost rate limit — cannot mute the hatch).
- Queue a slasher change (applies only after 60 days, longer than the ~38-day validator withdrawal window).
- Adjust the share of rewards that go to sequencers versus provers such that it is not economical for one of those actors to participate.
- Adjust the checkpoint reward to the same effect.

No residual action mutes the escape hatch.

### Why a Cooldown + Step Instead of a Rolling Window

A rolling window bounds cumulative change by re-anchoring to the value at window start; a cooldown-plus-step bounds it by a per-update ratio plus a minimum inter-update delay. For a single parameter, the latter is simpler (one timestamp of state, one revert path) and harder to get wrong than window-position/step interactions.

## Backwards Compatibility

1. **ABI**: `setSlasher` → `queueSetSlasher` / `cancelSetSlasher` / `finalizeSetSlasher`. `setLocalEjectionThreshold` removed. `updateEscapeHatch` → `setEscapeHatch`. `EscapeHatchUpdated` → `EscapeHatchSet`. `LocalEjectionThresholdUpdated` removed. New events `PendingSlasherQueued`, `PendingSlasherCancelled`. `setRewardConfig` SHALL no longer accept or write `rewardDistributor` / `rewardBooster`; its parameter type narrows to `MutableRewardConfig` (sequencer split / checkpoint reward only). `IRewardDistributor` gains `availableTo(address)`, `subsidizeAddress(address,uint256)`, `recoverFrom(address,address,uint256)`, and `recoverWrongAsset(address,address,uint256)`; the prior `recover(address,address,uint256)` is removed. `claim` authorization changes from `msg.sender == canonicalRollup()` to `amount <= availableTo(msg.sender)`.
2. **Timing**: Slasher replacements take effect 60 days after queueing.
3. **Parameter constraints**: `setProvingCostPerMana` reverts on cooldown violation, step violation, or `v < 2`. `updateStakingQueueConfig` reverts on zero flush fields (matching the existing constructor invariant).
4. **Escape hatch finality**: `setEscapeHatch` is final for the life of the rollup; deployers must verify the address before calling.
5. **Reward endpoint finality**: `rewardDistributor` and `rewardBooster` are final for the life of the rollup; deployers must verify both contracts before construction.

## Test Cases

1. **Escape hatch one-shot**: `setEscapeHatch(nonZero)` succeeds once; second call reverts with `EscapeHatchAlreadySet`; zero-address call reverts with `EscapeHatchCannotBeZero`.
2. **Reward address immutability**: no reachable post-deployment path mutates `RollupStore.config.rewardDistributor` or `RollupStore.config.rewardBooster`; `setRewardConfig` cannot write either field.
3. **Per-address subsidy path**: after a second rollup is registered as canonical, `subsidizeAddress(oldRollup, amount)` credits `availableTo(oldRollup)` without reducing `availableTo(newCanonical)`; the old rollup proves an epoch and successfully claims up to its subsidy; the canonical rollup cannot draw from another address's `specificRecipientBalance`; `recoverFrom` cannot drive `availableTo(canonicalRollup())` negative; `recoverWrongAsset` reverts when called with `ASSET`.
4. **Proving cost floor / step / cooldown**: `setProvingCostPerMana(0|1)` reverts with `ProvingCostBelowFloor`; from 1000, setting 1501 or 666 reverts with `ProvingCostStepExceeded`, while 1500 / 667 succeed; the first post-init update lands immediately, a second within 30 days reverts with `ProvingCostCooldown`.
5. **Flush-size invariants on update**: `updateStakingQueueConfig` with zero `normalFlushSizeMin` or `normalFlushSizeQuotient` reverts.
6. **Slasher queue flow**: `queueSetSlasher` / `cancelSetSlasher` are owner-only; `finalizeSetSlasher` is permissionless, reverts before 60 days with `SlasherNotReady`, and applies the change after. Queue overwrite resets the timer; cancel without a pending queue reverts with `NoPendingSlasher`.
7. **`setLocalEjectionThreshold` removed**: selector is not reachable on the deployed rollup.

## Security Considerations

### Reward Endpoint Immutability

Because `rewardDistributor` and `rewardBooster` are set at construction and never mutated, the rollup does not need to defend against reverts, return-bombs, gas repricing, adversarial return values, or re-entrancy from these endpoints beyond what holds at deployment time. Deployers MUST audit both contracts before construction; a misdeployment is unrecoverable without redeploying the rollup via `Registry.addRollup`.

### Per-Address Subsidy Isolation

`RewardDistributor.totalEarmarkedBalance` isolates earmarked balances from the canonical rollup's implicit pool, so `subsidizeAddress(recipient, amount)` cannot reduce `availableTo(canonicalRollup())`. `recoverFrom` shares the same accounting path as `claim`, so governance recovery cannot drive `availableTo(canonicalRollup())` negative; `recoverWrongAsset` refuses `ASSET` and therefore cannot bypass that accounting. `subsidizeAddress` is permissionless; any party can fund an arbitrary address, but funds so committed are only withdrawable by that address via `claim` (or by governance via `recoverFrom`).

### Rate Limit and Queue Bypass

The cooldown check anchors on `provingCostLastUpdate`, so multicalls and repeated proposals within a window MUST revert. The step bound is symmetric so governance cannot deflate proving cost to the floor in one step either. The slasher queue resets its timer on overwrite, so governance cannot accrue "credit" from a cancelled queue.

### Escape Hatch Finality

The one-shot `setEscapeHatch` is load-bearing for the exit guarantee and cannot be reversed. A misconfigured first call is unrecoverable — deployers MUST verify the address and implementation before calling.

### Future Rollup Versions

New rollups deployed via `Registry.addRollup()` MUST carry the same or stricter versions of these constraints. Relaxing any of them on a future rollup would weaken the exit guarantee for its users.

## Copyright Waiver

Copyright and related rights waived via [CC0](/LICENSE).
