# Aztec Improvement Proposal: Deploy v6 With a 90% Sequencer Reward Share

## Preamble

| `azip` | `title` | `description` | `author` | `discussions-to` | `status` | `category` | `created` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 30 | Deploy v6 With a 90% Sequencer Reward Share | Deploys the v6 rollup with `sequencerBps` 9,000 instead of 7,000, cutting redundant prover L1 spend funded by selling $AZTEC. | Koen van Marrewijk (@koenmtb1) | N/A | Approved | Economics | 2026-09-24 |

## Abstract

The canonical rollup splits each checkpoint reward between the sequencer (`sequencerBps`) and the epoch's prover pool (the remainder). Today `sequencerBps` is 7,000, so 30% of every checkpoint reward (150 of 500 $AZTEC) goes to provers. The prover pool is shared among every `proverId` that submits a proof. This rewards running many prover identities, and each identity's proof is verified separately on L1. Over the last 30 days, about 50 proofs were verified per epoch, from about 52 active `proverId`s per day. The L1 gas for those proofs averaged ≈0.55 ETH/day, which is about 95,000 $AZTEC/day or roughly half the prover pool. That ETH has to be funded, most likely by selling $AZTEC.

This AZIP proposes that the **v6 rollup be deployed with `sequencerBps = 9000`**, and that it ship as part of the v6 upgrade AZUP. **It does not modify the reward configuration of any existing rollup, and it requires no `setRewardConfig` governance action.** The v5 rollup keeps 7,000 for as long as it is canonical. The new split takes effect when v6 is promoted to canonical. `checkpointReward` (500 $AZTEC) and fee-based prover revenue (`provingCostPerMana`) stay the same, and no contract code changes are needed.

## Impacted Stakeholders

**Provers**: Primary stakeholder. From v6 onwards, the block-reward prover pool falls from 4,800 to 1,600 $AZTEC per epoch, a 66.7% cut. Fee-based prover revenue (`manaUsed × provingCostPerMana`) is unchanged. We expect marginal and redundant provers not to carry over to v6, or to leave soon after. Consistent provers keep the largest share under the `RewardBooster` curve from [AZIP-5](./azip-5.md) and the full-epoch activity rule from [AZIP-25](./azip-25.md). Because the change arrives with a scheduled upgrade, provers have the whole AZUP review and signaling period to adjust capacity.

**Sequencers**: On v6, the default sequencer reward rises from 350 to 450 $AZTEC per checkpoint (+28.6%). Sequencer L1 costs are unchanged.

**Tokenholders**: Emissions do not change. What changes is who receives them. Less goes to actors who must sell $AZTEC to pay L1 gas, and more goes to stakers who can restake or hold. Tokenholders approve the change as part of the v6 AZUP vote.

**Staking providers using registry reward overrides**: Overrides are applied as `min(defaultSequencerReward, override)`. On v6, an override set between 350 and 450 $AZTEC would start to bind at the new default. Overrides below 350 are unaffected.

**Infrastructure providers / indexers**: Reward dashboards and APR calculators that hardcode the 70/30 split need a per-rollup-version value. There are no ABI changes.

## Motivation

### Current configuration (verified onchain, 2026-09-24)

| Item | Value |
| --- | --- |
| Registry | `0x35b22e09ee0390539439e24f06da43d83f90e298` |
| Canonical rollup (v5, `Registry.getCanonicalRollup()`) | `0x91ff8bbd8ebb07893010d50a48a1609e5ebd8e34` |
| Rollup owner (= `Registry.getGovernance()`) | `0x1102471eb3378fee427121c9efcea452e4b6b75e` |
| `getRewardConfig().sequencerBps` | **7,000** |
| `getRewardConfig().checkpointReward` | 500e18 (500 $AZTEC) |
| Epoch duration | 32 slots × 72 s = 38.4 min |
| Checkpoints per epoch / epochs per day | 32 (one per slot) / 37.5 (= 86,400 s ÷ 2,304 s) |
| Checkpoints per day | 1,200 (= 32 × 37.5 = 86,400 s ÷ 72 s) |
| `proofSubmissionEpochs` | 1 |

The same value (`sequencerBps = 7000`) is hardcoded in `RollupConfiguration.getRewardConfiguration()` (`l1-contracts/script/deploy/RollupConfiguration.sol` in `aztec-packages`). Unless it is changed, v6 will inherit the same split.

### The problem: a redundant proving race paid for in ETH

`RewardLib.handleRewardsAndFees` pays the prover pool of an epoch to every `proverId` that submits a valid proof for it, weighted by `RewardBooster` shares. Each proof is verified on L1 on its own, at about 1.75M gas for a single-proof `submitEpochRootProof` transaction. Only one proof per epoch is needed to advance the proven chain. Every proof after the first adds no safety to the network, but it still costs ETH.

The table below covers every `L2ProofVerified` event on the canonical rollup over the last 30 days (2026-08-25 to 2026-09-23). Gas figures come from a 1-in-6 sample of the transaction receipts (7,375 transactions).

| Metric | Value |
| --- | --- |
| Proofs verified | 56,193 (≈1,870/day, ≈50 per epoch) |
| Active `proverId`s per day | 46–57 (median 52), 71 distinct over 30 days |
| L1 transactions | 44,252 (some carry several proofs) |
| Gas per proof | ~1.65M on average (~1.75M when submitted alone, ~1.5M in 6–7-proof bundles) |
| Effective gas price paid | median 0.087 gwei, gas-weighted mean 0.18 gwei, p90 0.35 gwei |
| Daily gas-weighted mean price | 0.07–0.45 gwei |
| L1 cost per proof | ≈0.00029 ETH |
| Total ETH spent | ≈16.4 ETH (≈0.55 ETH/day, daily range 0.20–1.14 ETH) |

The picture is the same over the full life of the v5 rollup (2026-07-15 to 2026-09-23, 71 days): ≈0.58 ETH/day on average, with a median of ≈0.46 ETH/day. Spikes in L1 gas (for example 2026-08-19 to 08-24) pushed single days to 1.8–2.8 ETH.

The number of operators does not drive L1 cost. The number of proofs does, because bundling barely reduces gas per proof. The shares for a `proverId` depend only on that ID's own `RewardBooster` score, so an operator can raise its slice of the pool by running more IDs. Adding an ID pays off as long as its share of the pool is worth more than the gas for one more proof.

The block-reward prover pool is 30% × 500 $AZTEC × 32 checkpoints = 4,800 $AZTEC per epoch. At 37.5 epochs per day, that is 180,000 $AZTEC per day. At ~0.0000058 ETH per $AZTEC (both the 30-day average and the 2026-09-24 price, ~$0.0156), that is **≈1.04 ETH/day**. Provers spent **≈0.55 ETH/day** on L1 verification alone over the last 30 days. Using each day's $AZTEC/ETH price, that is **≈95,000 $AZTEC/day, or about 53% of the pool**, before any proving hardware costs.

This is what a free-entry equilibrium looks like. New `proverId`s keep appearing, from new operators or from existing operators adding IDs, until one more proof's cost (L1 gas plus hardware) roughly equals the share it earns. Gas alone takes about half of the pool, and the rest pays for hardware and margin. A larger pool does not buy more security or more independent operators. It buys more duplicate proofs. The ETH for those proofs has to come from somewhere. If provers fund it from rewards, that means up to ~95,000 $AZTEC sold per day. This selling is structural and happens even at today's very low gas prices (median 0.087 gwei). When L1 gas rises, the same number of proofs needs even more $AZTEC sold: on the worst days of the sample it was 2–5× the average.

## Specification

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119 and RFC 8174.

This AZIP is implemented **as part of the v6 rollup deployment**, not through a reward-config update on an existing rollup.

1. The v6 rollup MUST be constructed with an initial `RewardConfig` in which `sequencerBps = 9000`. This value is written once by `RewardLib.initializeConfig` during construction.
2. `checkpointReward` MUST remain 500e18 in the v6 initial `RewardConfig`, unless another AZIP bundled in the same AZUP explicitly changes it.
3. The v6 deployment configuration (`RollupConfiguration.getRewardConfiguration()` or its v6 successor) SHALL set `sequencerBps = 9000`.
4. The v6 upgrade AZUP SHOULD list this AZIP in `azips-included`, so tokenholders vote on the new split together with the rest of the v6 upgrade.
5. This AZIP MUST NOT be implemented by calling `setRewardConfig` on the v5 rollup (`0x91ff8bbd8ebb07893010d50a48a1609e5ebd8e34`) or on any other existing rollup. v5 keeps `sequencerBps = 7000` for the rest of its life, including any period after v6 is promoted during which v5 provers and sequencers are still paid from earmarked `RewardDistributor` subsidies.
6. No other parameters, contracts, or formulas are modified. `RewardBooster` parameters, `provingCostPerMana`, and the protocol fee margin are out of scope.

## Rationale

**Why ship it with v6 instead of updating v5?**

- *No governance action on a live reward config.* A new rollup takes its reward configuration at construction. Setting the value there avoids a standalone `setRewardConfig` proposal, including the risk of that call silently overwriting `checkpointReward` with a wrong value.
- *One vote, one review cycle.* The split is reviewed and voted on together with the other v6 changes, instead of needing its own AZUP, signaling round, and governance delay.
- *Predictable for operators.* Provers and sequencers already plan their capacity around the v6 migration. Tying the change to that date gives them a clear, known cutover instead of a mid-version change to their economics.
- *Consistent with where governance is heading.* v4 ownership was renounced ([AZIP-3](./azip-3.md)) to make that rollup immutable. If v5 follows the same path, its reward config cannot be changed at all, and a new deployment is the only route anyway.

The tradeoff is timing. Redundant prover spend and the related $AZTEC selling go on until v6 becomes canonical. If v6 is far away, governance could still choose a separate `setRewardConfig` action on v5. That is not what this AZIP proposes.

**Why cut the prover share rather than change proof submission rules?** A protocol change that limits rewards to the first N proofs, or rewards only the first prover (see the attribution work in [AZIP-24](./azip-24.md)), would address the redundancy directly. However, it needs new contract logic plus audits. Changing the deployment value of `sequencerBps` needs neither. It also leaves room for a structural fix in a later version.

**Why 9,000?** At 9,000 the pool is 1,600 $AZTEC (≈0.0093 ETH) per epoch. At the 30-day gas-weighted mean (0.18 gwei), one proof costs ≈0.0003 ETH, so the pool still covers the L1 cost of about 32 proofs per epoch. Even at 0.45 gwei, the worst daily average in the last 30 days, it covers about 12. That is well above the one proof needed for liveness. 9,000 is also a round figure that keeps 10% of emissions tied to proving, which keeps provers engaged.

**Alternatives considered:**

- *8,000 (prover pool 3,200 $AZTEC per epoch)*: A more conservative step with more room for gas spikes. It removes only half as much structural selling.
- *10,000 (no block reward for provers)*: Provers would rely entirely on fee revenue, which is too small at current usage to guarantee liveness.
- *Lowering `checkpointReward`*: This reduces emissions for sequencers as well and does not fix the imbalance between the two roles.
- *`setRewardConfig` on v5 now*: This takes effect sooner but needs its own governance action on a live rollup. It is rejected in favor of the v6 path described above.

**Why sequencers?** Sequencers must stake and produce checkpoints every slot. Their L1 cost per checkpoint is fixed and does not scale with how many of them take part. Giving the extra rewards to them adds no duplicated L1 spend.

## Backwards Compatibility

Fully backwards compatible. The change only affects the initial configuration of a new rollup deployment (v6). There are no ABI, storage-layout, or contract-code changes. The v5 rollup and its reward configuration are untouched, and rewards on v5 continue at 70/30 for as long as v5 pays them out. Off-chain tools SHOULD read `getRewardConfig()` from each rollup version instead of hardcoding a split.

## Test Cases

Using `defaultSequencerReward = checkpointReward × sequencerBps / 10_000` and `proverReward = checkpointReward − defaultSequencerReward`:

| Rollup | `checkpointReward` | `sequencerBps` | Sequencer / checkpoint | Prover pool / checkpoint | Prover pool / epoch (32 checkpoints) |
| --- | --- | --- | --- | --- | --- |
| v5 (unchanged) | 500e18 | 7,000 | 350e18 | 150e18 | 4,800e18 |
| v6 (proposed) | 500e18 | 9,000 | 450e18 | 50e18 | 1,600e18 |

Deployment assertions (a deploy-config test, e.g. alongside `DeployConfigValidation.t.sol`, plus a post-deployment check):

1. `RollupConfiguration.getRewardConfiguration(...).sequencerBps == 9000`.
2. On the deployed v6 rollup: `getRewardConfig().sequencerBps == 9000` and `getRewardConfig().checkpointReward == 500e18`.
3. On v5 (`0x91ff8bbd8ebb07893010d50a48a1609e5ebd8e34`), before and after v6 promotion: `getRewardConfig().sequencerBps == 7000`, meaning it was not modified.
4. The v6 upgrade payload contains no call to `setRewardConfig`.

## Reference Implementation

Change to the deployment configuration in `aztec-packages` (`l1-contracts/script/deploy/RollupConfiguration.sol`) for the v6 release:

```diff
   function getRewardConfiguration(IRewardDistributor _rewardDistributor) external pure returns (RewardConfig memory) {
     uint16 sequencerBps;
     uint96 checkpointReward;
-    sequencerBps = 7000;
+    // AZIP-30: 90/10 sequencer/prover split from v6 onwards.
+    sequencerBps = 9000;
     checkpointReward = 500e18;
```

Update the matching expectation in `l1-contracts/test/script/DeployConfigValidation.t.sol` (`sequencerBps: Bps.wrap(7000)` → `Bps.wrap(9000)`).

## Economics Considerations

Figures assume a checkpoint in every slot (37.5 epochs, 1,200 checkpoints per day) and ~0.0000058 ETH per $AZTEC (30-day average). They apply from the moment v6 becomes canonical.

| | v5 (7,000) | v6 (9,000) | Δ |
| --- | --- | --- | --- |
| Total emissions / day | 600,000 $AZTEC | 600,000 $AZTEC | 0 |
| Sequencers / day | 420,000 | 540,000 | +120,000 |
| Prover pool / day | 180,000 (≈1.04 ETH) | 60,000 (≈0.35 ETH) | −120,000 |
| Prover pool / epoch | 4,800 (≈0.028 ETH) | 1,600 (≈0.0093 ETH) | −3,200 |

**Sell pressure.** Over the last 30 days, prover L1 gas cost ≈0.55 ETH/day, which is ≈95,000 $AZTEC/day and about 53% of the pool. At 9,000, the whole pool (≈0.35 ETH/day) is smaller than today's gas bill, so the number of proofs per epoch has to fall. If gas keeps taking about the same share of a smaller pool, prover gas spend falls to ≈0.18 ETH/day (≈32,000 $AZTEC/day). That is a reduction of **≈63,000 $AZTEC/day (≈0.37 ETH, ≈$1,000/day at current prices)** in selling needed to fund L1 gas, with ~95,000 $AZTEC/day as the upper bound. These figures assume provers fund gas by selling rewards. Provers that fund gas from other sources sell less today, so the real reduction would be smaller. The 120,000 $AZTEC/day taken from the prover pool goes to sequencers; it is not removed from emissions. The net reduction in selling depends on sequencers selling a smaller share of their rewards than provers do. That is expected, because sequencers have no per-epoch ETH cost that grows with competition. Because the prover set has to re-form on v6 anyway, the new equilibrium should be reached faster than it would be after a change in the middle of a version.

**Proofs per epoch.** How many proofs per epoch the pool can pay L1 gas for depends on the L1 gas price. This caps the number of `proverId`s that break even on gas, whether they are run by separate operators or by one operator:

| L1 gas price | Cost per proof (1.65M gas) | Proofs covered by pool (7,000) | Proofs covered by pool (9,000) |
| --- | --- | --- | --- |
| 0.087 gwei (30-day median) | 0.00014 ETH | ~194 | ~65 |
| 0.18 gwei (30-day gas-weighted mean) | 0.0003 ETH | ~95 | ~32 |
| 0.45 gwei (worst day, last 30 days) | 0.00074 ETH | ~37 | ~12 |
| 1 gwei | 0.00165 ETH | ~17 | ~5.6 |
| 3 gwei | 0.00495 ETH | ~5.6 | ~1.9 |
| 10 gwei | 0.0165 ETH | ~1.7 | <1 |

For comparison, over the last 30 days ~50 proofs were verified per epoch, about half the gas-only break-even of ~95. The gap is what hardware and margin cost. These numbers exclude proving hardware costs and fee-based prover revenue. Bundling proofs into one transaction lowers gas per proof only slightly (~1.5M vs ~1.75M), so the figures change little for bundled operators. They also assume v6 proof verification costs about the same gas as v5. If v6 changes the verifier, these figures should be recomputed before the AZUP.

**Long-term.** Reward-distributor runway is unchanged, because total emissions do not change. As network usage grows, fee-based prover revenue (`manaUsed × provingCostPerMana`) grows with it and gradually replaces block rewards as the main income for provers.

## Security Considerations

- **Prover liveness under high L1 gas.** This is the main risk. If no valid epoch proof lands within `proofSubmissionEpochs` (currently 1), unproven checkpoints are pruned. At 9,000, the block-reward pool covers fewer than one ~1.65M-gas proof once L1 gas stays above roughly 5–6 gwei for long periods, before hardware costs. That is more than 10× the worst daily average in the last 30 days. Mitigations: (a) fee-based prover revenue is unchanged and rises with L1 costs through `provingCostPerMana`; (b) while governance owns v6, `sequencerBps` can be lowered with a single owner-gated `setRewardConfig` call. If v6 ownership is ever renounced, this lever disappears, and the split should be reviewed again before renouncing.
- **Migration-window liveness.** Around the v5→v6 cutover, provers decide whether to run v6 based on the new, lower pool. Operators and the AZUP authors SHOULD confirm that enough prover capacity has committed to v6 before promotion.
- **Prover centralization.** Fewer proofs per epoch is the intended outcome. Liveness depends on the number of independent operators, not the number of `proverId`s. Reviewers SHOULD check that the reduced pool still supports several independent operators and does not just shrink the ID count of each one. The `RewardBooster` curve from [AZIP-5](./azip-5.md) already favors consistent operators. The network needs only one honest prover per epoch for liveness, and proof validity is enforced by the L1 verifier regardless of how many provers there are.
- **No smart-contract risk and no live-config mutation.** The value is set once at construction through the existing `initializeConfig` path, which enforces `sequencerBps ≤ 10_000`. No governance payload touches an existing rollup's reward config, which removes the risk of a `setRewardConfig` call overwriting `checkpointReward` by mistake. The main implementation risk is a wrong value in the deploy script, which the Test Cases cover.
- **Governance scope.** [AZIP-2](./azip-2.md) lists changing the sequencer/prover split as a power that can make one role uneconomical. This proposal exercises that power on purpose and within limits, through the normal upgrade vote. It keeps 10% of emissions for provers and does not set the prover share to zero.
- **Registry reward overrides.** Because overrides are capped at `min(default, override)`, raising the default cannot increase rewards past an override. On v6 it only affects overrides set between 350 and 450 $AZTEC.

## Copyright Waiver

Copyright and related rights waived via [CC0](/LICENSE).
