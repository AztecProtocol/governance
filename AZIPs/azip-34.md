# AZIP-34: Sustain the v5 Rollup After v6 Becomes Canonical

## Preamble

| `azip` | `title` | `description` | `author` | `discussions-to` | `status` | `category` | `created` | `requires` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 34 | Sustain the v5 Rollup After v6 Becomes Canonical | Cuts the v5 `checkpointReward` to 50 AZTEC and earmarks 1.8M AZTEC so v5 keeps being sequenced and proven for 30 days after v6. | Koen van Marrewijk (@koenmtb1) | N/A | Draft | Economics | 2026-10-06 | [AZIP-2](./azip-2.md) |

## Abstract

When the v6 rollup becomes canonical, the v5 rollup loses access to the implicit reward pool in the `RewardDistributor`, so its checkpoint rewards drop to zero. Without rewards, provers have little reason to keep proving v5, and users and applications still migrating off v5 could be left on a chain that stops finalizing. This AZIP lowers the v5 `checkpointReward` from 500 AZTEC to 50 AZTEC and earmarks 1,800,000 AZTEC for the v5 rollup in the `RewardDistributor`, using the per-address subsidy path from [AZIP-2](./azip-2.md). At one checkpoint per 72-second slot, that budget funds v5 at the reduced rate for 30 days. Both changes are carried out by the v6 upgrade payload (`V6UpgradePayload`), in the same transaction that makes v6 canonical and before it does so.

## Impacted Stakeholders

**Sequencers.** Sequencers that stay on v5 (deposits made with `moveWithLatestRollup = false`) keep earning checkpoint rewards after v6 becomes canonical, at 10% of the current rate: 35 AZTEC per checkpoint instead of 350. Sequencers that follow the latest rollup move to v6 and are unaffected by this AZIP. Once the earmarked budget is used up, v5 checkpoint rewards drop to zero, and v5 sequencers earn only transaction fees.

**Provers.** Provers of v5 epochs keep earning the prover share of checkpoint rewards: 15 AZTEC per checkpoint instead of 150. Rewards are paid on proof submission, so this budget is what keeps v5 epochs being proven while activity migrates to v6.

**Tokenholders.** 1.8M AZTEC of the roughly 91.0M AZTEC currently held by the `RewardDistributor` is set aside for v5. The rest stays in the implicit pool, which v6 inherits as the new canonical rollup. Governance can recover any unused earmarked balance later through `recoverFrom`.

**App developers, wallets, bridges and infrastructure providers.** v5 keeps producing and finalizing checkpoints for at least 30 days after v6 becomes canonical. That gives users and applications a proven chain to migrate from, and keeps withdrawals and L2-to-L1 messages from v5 working during the migration.

## Motivation

The `RewardDistributor` only lets the canonical rollup draw from its implicit (un-earmarked) pool. A non-canonical rollup can only claim funds earmarked to its address through `subsidizeAddress`. The distributor resolves the canonical rollup live from the Registry, so v5 loses pool access the moment `Registry.addRollup(v6)` executes. The v5 rollup's `rewardDistributor` is also immutable under [AZIP-2](./azip-2.md), so v5 can never be pointed at a different funding source.

Today nothing is earmarked for v5 (`totalEarmarkedBalance == 0`). The moment v6 becomes canonical, `availableTo(v5)` returns zero, and v5 checkpoint rewards stop entirely. v5 would then depend only on fees, which will fall quickly as activity moves to v6. The likely result is that proving stops, v5 stops finalizing, and funds and messages still in flight on v5 get stranded.

Leaving the current 500 AZTEC `checkpointReward` in place is not an option either. Funding 30 days at that rate would cost 18M AZTEC, which is far more than a network in wind-down needs. This AZIP sizes the v5 reward to what is needed to keep v5 live and proven, and funds exactly that.

## Specification

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119 and RFC 8174.

### Addresses

| Name | Address |
| --- | --- |
| v5 Rollup (`V5`) | `0x91fF8bbD8Ebb07893010D50A48A1609e5EBd8E34` |
| RewardDistributor (`DISTRIBUTOR`) | `0x555BaAc4757A89F1Ce0c84FA35AfE9dD7aA8e1D3` |
| AZTEC token (`ASSET`) | `0xa27ec0006e59f245217ff08cd52a7e8b169e62d2` |
| Governance | `0x1102471eb3378fee427121c9efcea452e4b6b75e` |
| v6 upgrade payload (`PAYLOAD`) | To be deployed with the v6 rollup |

v6 is deployed against the same `DISTRIBUTOR`, read from the Registry. No distributor migration is required.

### Parameter changes

| Parameter (v5 Rollup) | Current | New |
| --- | --- | --- |
| `checkpointReward` | 500 AZTEC (`500e18`) | 50 AZTEC (`50e18`) |
| `sequencerBps` | 7000 | 7000 (unchanged) |
| Earmarked for v5 in `DISTRIBUTOR` | 0 AZTEC | 1,800,000 AZTEC (`1_800_000e18`) |

These values are set on `PAYLOAD` as immutables at deployment: `EARMARK_AMOUNT = 1_800_000e18`, `RETUNE_PREDECESSOR_REWARDS = true`, `PREDECESSOR_SEQUENCER_BPS = 7000` and `PREDECESSOR_CHECKPOINT_REWARD = 50e18`. `PREDECESSOR` is the canonical rollup at deployment, which MUST be `V5`.

### Routing the earmark through the payload

Governance cannot call the `ASSET` contract (`Governance__CannotCallAsset`), so it cannot approve `DISTRIBUTOR` to pull tokens for `subsidizeAddress`. Instead, `PAYLOAD` itself receives the funds and makes the `subsidizeAddress` call. No additional contract is deployed.

`PAYLOAD` exposes `forwardEarmark()`, which:

- reads `amount = ASSET.balanceOf(PAYLOAD)`, so it can never disagree with the `recoverFrom` action that funds it;
- approves `DISTRIBUTOR` for `amount`;
- calls `DISTRIBUTOR.subsidizeAddress(PREDECESSOR, amount)`.

`forwardEarmark()` is permissionless. It can only push the payload's own balance to one fixed recipient, the v5 earmark, so anyone calling it can only add to that earmark.

### Governance actions

This AZIP is implemented by the following actions in `PAYLOAD.getActions()`. They MUST run in this order, after the predecessor guard and before any action that registers v6:

1. `PAYLOAD.assertPredecessorIsCanonical()`: reverts unless `V5` is still the canonical rollup. (Part of the v6 payload; listed because steps 2 to 4 rely on it.)
2. `DISTRIBUTOR.recoverFrom(V5, PAYLOAD, 1_800_000e18)`: v5 is still canonical, so the funds are drawn from the implicit pool and sent to `PAYLOAD`.
3. `PAYLOAD.forwardEarmark()`: earmarks the full 1.8M back to `V5` in `DISTRIBUTOR`.
4. `V5.setRewardConfig(MutableRewardConfig({sequencerBps: 7000, checkpointReward: 50e18}))`.
5. The v6 promotion actions specified by the v6 upgrade AZUP, including `Registry.addRollup(v6)`.

Steps 2 to 4 MUST NOT be executed in a separate proposal ahead of the v6 promotion. Lowering the reward early would cut v5 rewards while v5 is still the canonical rollup. Steps 2 and 3 MUST come before `Registry.addRollup(v6)`, because v5 can only draw from the implicit pool while it is canonical.

### Post-conditions

After the proposal executes:

- `V5.getCheckpointReward() == 50e18` and its `sequencerBps` is 7000.
- `DISTRIBUTOR.specificRecipientBalance(V5)` has increased by `1_800_000e18`.
- `DISTRIBUTOR.totalEarmarkedBalance()` has increased by `1_800_000e18`.
- `DISTRIBUTOR.availableTo(V5) == specificRecipientBalance(V5)`, since v5 is no longer canonical.
- The `ASSET` balances of Governance and `PAYLOAD` are the same as before execution.

## Rationale

**Sizing.** v5 runs 72-second slots, which is 1,200 checkpoints per day. At 50 AZTEC per checkpoint, 30 days costs 1,200 × 30 × 50 = 1,800,000 AZTEC. Thirty days matches the minimum period over which v5 is expected to stay live while users and applications migrate to v6.

**Why 50 AZTEC.** Once v6 is canonical, v5 needs to stay live and proven, not to compete for sequencers. A 90% cut keeps a meaningful incentive for provers and for the sequencers that stay behind, without spending treasury funds on a rollup being wound down.

**Why keep the 70/30 split.** Changing `sequencerBps` isn't needed to keep v5 live. Keeping it unchanged means reward computation stays exactly as it is today, just with a smaller total. The v6 split is set separately by the v6 deployment and is out of scope here.

**Why earmark in the existing distributor.** v5's `rewardDistributor` is immutable, so `DISTRIBUTOR` is the only source v5 can ever claim from. The [AZIP-2](./azip-2.md) subsidy path was designed for exactly this case: rewarding a rollup after it stops being canonical. Drawing from v5 and earmarking back to v5 looks circular but isn't: it turns pool access that is about to lapse into a balance keyed to v5's address, which survives v5 losing canonical status.

**Why the payload routes the funds.** Governance can move funds out of the distributor with `recoverFrom`, but it cannot call `ASSET.approve`. The upgrade payload is already a contract that Governance calls during execution, so making it the temporary recipient and the caller of `subsidizeAddress` completes the earmark in the same transaction, without a separate contract and without routing funds through an externally owned account.

**Alternative considered: funding from a third party.** `subsidizeAddress` is permissionless, so the Aztec Foundation or anyone else could fund the earmark directly. This AZIP funds it from the existing reward pool instead, so v5's continued operation doesn't depend on any single party. A third-party top-up remains possible later if v5 needs to run longer than 30 days.

## Backwards Compatibility

This AZIP makes no code changes to any deployed contract. It changes owner-configurable parameters on v5 and adds an earmark in the existing distributor. Its actions ship inside the v6 upgrade payload.

v5 sequencers and provers see checkpoint rewards fall by 90% from the moment the proposal executes. The split is read when an epoch is proven, so checkpoints proposed before the upgrade but proven after it are paid at the new rate, from the earmark. Once the earmark runs out, `RewardLib` finds `checkpointRewardsAvailable < checkpointRewardsDesired` and scales rewards down pro rata until they reach zero. Nothing reverts.

Any earmark left unused stays assigned to v5 until Governance recovers it with `recoverFrom(V5, …)`. v5's ownership MUST NOT be renounced as part of the upgrade, so that Governance keeps this and other recovery paths.

## Test Cases

Fork tests against mainnet state, executing the full v6 upgrade proposal through Governance:

1. Executing the payload succeeds, and all post-conditions listed under Specification hold.
2. After execution, submitting a proof for a v5 epoch pays out checkpoint rewards computed with `checkpointReward = 50e18`, split 70% to sequencers and 30% to provers. `specificRecipientBalance(V5)` decreases by exactly the amount claimed.
3. After execution, `DISTRIBUTOR.availableTo(v6)` equals the distributor's pre-execution balance minus all earmarked balances, including the new `1_800_000e18`.
4. Simulating 36,000 proven checkpoints on v5 drains the earmark to zero. The next proof submission succeeds and pays zero checkpoint rewards.
5. Calling `PAYLOAD.forwardEarmark()` from any address can only increase `specificRecipientBalance(V5)`, and only by the payload's own `ASSET` balance.
6. If another rollup becomes canonical before execution, the predecessor guard makes the whole proposal revert and no funds move.
7. Placing `Registry.addRollup(v6)` ahead of step 2 makes the proposal revert with `RewardDistributor__InsufficientAvailable`, because v5 is no longer canonical and has no earmark yet.

## Economics Considerations

| | Per checkpoint | Per day (1,200 checkpoints) | 30 days |
| --- | --- | --- | --- |
| Sequencers (70%) | 35 AZTEC | 42,000 AZTEC | 1,260,000 AZTEC |
| Provers (30%) | 15 AZTEC | 18,000 AZTEC | 540,000 AZTEC |
| **Total** | **50 AZTEC** | **60,000 AZTEC** | **1,800,000 AZTEC** |

**Treasury impact.** 1.8M AZTEC is about 2% of the roughly 91.0M AZTEC currently held in `DISTRIBUTOR`. It is a one-off allocation with a fixed ceiling. No new tokens are minted, and the pool v6 inherits is reduced by the same amount.

**Sequencer incentives.** Sequencer rewards are paid per proposed checkpoint, so each v5 sequencer's share depends on how many attesters remain on v5. Operators whose stake stays on v5 through a separate arrangement (for example stake lent to them for this purpose) keep the checkpoint rewards their sequencers earn. The reduced rate is not meant to make staking on v5 profitable. It is meant to cover the cost of running nodes while v5 is wound down.

**Prover incentives.** At 15 AZTEC per checkpoint, a 32-slot epoch carries 480 AZTEC of prover rewards on top of any fees. That is the main incentive to keep proving v5 once transaction volume moves to v6. If proving turns out to be uneconomic at this rate, a follow-up proposal MAY raise the rate within the same earmark, which would shorten how long the budget lasts.

**Budget start.** Checkpoints proposed before the upgrade but not yet proven are paid from the earmark at the new rate. This draws slightly on the 30-day budget, by at most the checkpoints in the proof submission window at the time of the upgrade.

**Beyond 30 days.** If v5 still needs to run once the earmark is exhausted, it can be topped up permissionlessly with `subsidizeAddress(V5, amount)`, or by a further proposal. Unused funds can be recovered by Governance.

## Security Considerations

**Ordering and atomicity.** If steps 2 to 4 ran before v6 was promoted, v5 would have its rewards cut while it is still the canonical rollup. If the v6 promotion ran without them, v5 would get no rewards at all. Bundling everything into the v6 upgrade payload, in the specified order, removes both risks. `Governance.execute` requires every action to succeed in one transaction, so a failure at any step leaves no funds moved and no parameters changed. A wrong ordering makes step 2 revert rather than leaving v5 unfunded.

**Predecessor guard.** `recoverFrom(V5, …)` only draws from the implicit pool while v5 is canonical. The payload's predecessor guard runs first and confirms that, so the draw cannot silently fall back on some other balance.

**Payload as a transit address.** `PAYLOAD` holds `ASSET` only between steps 2 and 3 of a single transaction. `forwardEarmark()` sends its full balance into the v5 earmark and nowhere else. It is permissionless on purpose: tokens sent to the payload by mistake can still be pushed into the earmark rather than being stranded. The payload SHOULD be verified on a block explorer and reviewed before signalling.

**Governance deposits untouched.** No funds pass through the Governance contract's `ASSET` balance, so voter deposits and withdrawal accounting are unaffected.

**Earmark accounting not enforced on-chain.** `subsidizeAddress` is permissionless, so the payload does not assert a specific `totalEarmarkedBalance`; otherwise a 1-wei subsidy from anyone could block the upgrade. Reviewers SHOULD check the distributor's earmarked balances just before execution.

**Earmark exhaustion.** When the earmark runs out, v5 rewards scale down to zero without reverting, so `submitEpochRootProof` keeps working. From then on v5 depends on fees alone for proving. v5's escape hatch still gives users an exit path if proving stops. Integrators SHOULD finish migrating to v6 within the 30-day window.

**Residual control over v5.** Governance remains the owner of v5 and can change `checkpointReward` again with a future proposal. `setRewardConfig` has no cooldown or step limit, so the change lands as soon as the payload executes. The other constraints from [AZIP-2](./azip-2.md) continue to apply.

**Reward concentration.** A small v5 validator set means fewer, larger reward shares. That doesn't affect v5's safety, since attestation and slashing rules are unchanged. It does mean that in the extreme case, a handful of operators run v5 on their own.

## Copyright Waiver

Copyright and related rights waived via [CC0](/LICENSE).
