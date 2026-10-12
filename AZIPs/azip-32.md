# AZIP-32: Staking rewards for locked tokens

## Preamble

| `azip` | `title` | `description` | `author` | `discussions-to` | `status` | `category` | `created` | `requires` |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 32 | Staking rewards for locked tokens | Set sequencer checkpoint rewards to zero for positions staked through insider lockup contracts. | Zac Williamson (@zac-williamson) | https://github.com/AztecProtocol/governance/discussions/76 | Draft | Economics | 2026-10-01 | AZIP-31 |

## Abstract

This proposal uses the Pluggable Sequencer Reward Calculator specified in [AZIP-31](./azip-31.md) to set sequencer checkpoint rewards to zero for positions held through insider lockup contracts (ATPs). It applies only to allocations held by employees of the Aztec Foundation and Aztec Labs, and investors of Aztec Labs. These positions remain stakeable, with governance participation, committee duties, slashing exposure and transaction-fee entitlement unchanged. Unlocked tokens withdrawn from the affected ATPs can be staked to earn the default sequencer checkpoint reward.

## Impacted Stakeholders

**Employees and investors.** Employees of the Aztec Foundation and Aztec Labs, and investors of Aztec Labs, would receive no sequencer checkpoint rewards on positions held through the affected insider ATP contracts. Ownership and unlock schedules remain unchanged. Unlocked tokens withdrawn from those contracts can be staked to earn the same sequencer checkpoint reward as everyone else.

**Sequencer operators.** Operators of affected delegated positions lose the commission associated with sequencer checkpoint rewards. Transaction fees remain available. V6 allows operators to exit delegated sequencer positions.

**Other stakers.** Genesis sequencers and Aztec sale participants remain eligible for sequencer checkpoint rewards. Their yield remains sensitive to the size of the staking set, including any locked-token positions that continue to participate.

**Provers and network users.** The configured prover reward share is unchanged. The calculator adds gas to proof submission, paid by the prover, within the limits specified in AZIP-31. Operator participation and committee availability affect block production and therefore applications and network users.

## Motivation

Locked tokens have almost no opportunity cost of staking.

A holder of liquid tokens who stakes gives up real alternatives: selling, providing liquidity, lending, or deploying capital somewhere else entirely. That holder has a reservation yield. Below it, staking is not worth the lockup, the operational burden, and the slashing risk, and they will not stake.

A holder of locked tokens has none of these alternatives. Therefore locked tokens stake at essentially any yield.

This would not matter much if locked tokens were a rounding error. They are not. They are a significant portion of the total supply and if they stake in size, they would push yields significantly down for independent, non-insider stakers who are much more yield sensitive.

In other words, insiders receiving rewards would crowd out the set of stakers that is precisely vital for a credibly neutral network to attract.

## Specification

The policy calculator implements the interface specified in AZIP-31. For each proposer supplied by the rollup, it returns:

- **Zero** where the position resolves to an ATP in an affected insider registry, whether the position is self-operated or delegated.
- **`defaultReward`** for all other positions, including genesis sequencers and Aztec sale participants.

The affected ATPs are those holding employee allocations for the Aztec Foundation or Aztec Labs, or investor allocations for Aztec Labs. The calculator resolves each proposer through `GSE.getWithdrawer(proposer)` → ATP staker's `getATP()` → ATP's `getRegistry()`, following the [AZIP-31 reference reduction calculator](https://github.com/AztecProtocol/aztec-packages/pull/25572). The rollup carries no additional classification logic.

The affected Ethereum mainnet ATP registries and their configured sequencer checkpoint rewards are:

| ATP factory | ATP registry | Reward |
| --- | --- | --- |
| [MATP factory: `0x23D5e1fb8315fc3321993C272F3270712e2d5c69`](https://etherscan.io/address/0x23D5e1fb8315fc3321993C272F3270712e2d5c69#readContract) | `0xD938bE4A2cB41105Bc2FbE707dca124A2e5d0c80` | Zero |
| [LATP factory: `0x278f39b11B3DE0796561E85cb48535c9f45dDfCc`](https://etherscan.io/address/0x278f39b11b3de0796561e85cb48535c9f45ddfcc#readContract) | `0x667d2641cb96734f386adA6A9afCF07B1815fB8b` | Zero |

Each registry address is returned by its factory's `getRegistry()`. ATP type alone does not determine reward eligibility; sale ATPs use separate registries. Unconfigured registries and positions for which the lookup fails receive `defaultReward`. Calculator configuration is controlled by Aztec governance.

Tokens that have unlocked but remain held through an affected ATP retain the zero-reward treatment. Tokens withdrawn and staked outside those ATPs receive `defaultReward`.

The global checkpoint reward and sequencer/prover split are unchanged. Distribution, prover rewards, transaction fees, calculator call limits and fallback behavior follow AZIP-31. Foregone sequencer rewards remain in the RewardDistributor; they are not redistributed to other sequencers.

The policy does not change staking eligibility, governance participation, committee duties, slashing, token ownership or unlock schedules.

Activation requires the AZIP-31 mechanism and a subsequent AZUP that sets the rollup's `sequencerRewardCalculator` to the policy calculator. This policy is not activated by deploying V6 with no calculator configured.

The calculator and classification state at proof submission determine reward treatment. Checkpoints proposed before activation but first rewarded by a proof submitted after activation therefore receive the new treatment. Rewards already credited are not reversed.

## Rationale

Removing checkpoint rewards removes the associated income for locked holders and the associated commission for their operators. This economically discourages locked-token staking without prohibiting it. The Economics Considerations below set out the effect of locked-token participation, increased issuance, reduced rewards and locked rewards.

### Arguments against this proposal

“Insiders bear the same operational cost and slashing risk, and should be paid for it.”

This is true and our answer is that they continue to be paid for it out of transaction fees, which is compensation for real work on real usage.

“It sets a precedent for the protocol selectively pricing rewards by identity.”

Differentiated rewards allow Aztec governance to align incentives with network objectives, including grant conditions or specified actions by holders. This proposal applies that principle to locked insider allocations, which have almost no opportunity cost of staking and are large relative to the token supply. Removing their checkpoint rewards supports participation by independent, yield-sensitive stakers and avoids increasing issuance to offset insider dilution. The reward policy is subject to Aztec governance.

## Backwards Compatibility

This changes checkpoint reward treatment for the affected insider ATP positions after activation. All other treatment remains as specified above. Once the AZIP-31 mechanism is deployed, activating this policy requires no further rollup deployment.

## Test Cases

The implementation should demonstrate the following outcomes:

| Case | Required outcome |
| --- | --- |
| Self-operated position held through an affected insider ATP | Zero sequencer checkpoint reward; transaction-fee entitlement and slashing remain unchanged. |
| Delegated position held through an affected insider ATP | Zero sequencer checkpoint reward and no operator commission from that reward. |
| Operator exits an affected delegated position using V6 | Position exits through the applicable exit process; exit does not unlock the underlying tokens early. |
| Unlocked tokens remain held through an affected ATP | Sequencer checkpoint reward remains zero. |
| Unlocked tokens are withdrawn and staked outside the affected ATP | Same sequencer checkpoint reward as other eligible stake. |
| Genesis sequencer, sale participant or other unaffected position | Existing reward treatment is unchanged. |
| Prover reward | Unchanged by the insider sequencer reward configuration. |
| Mixed batch of affected and unaffected proposers | Calculator returns zero for affected positions and `defaultReward` for unaffected positions, in checkpoint order. |
| Distributor draw for an affected checkpoint | Foregone sequencer reward remains in the RewardDistributor; configured prover share and transaction fees are preserved. |
| Affected checkpoint proposed before activation and first rewarded after activation | Zero sequencer checkpoint reward. |
| Reward credited before activation | Previously credited reward is not reversed. |
| ATP or registry lookup fails | `defaultReward`, as specified by the reference reduction calculator. |

## Economics Considerations

### Baseline and assumptions

The model uses a total supply of 10.35B AZTEC and a sellable supply, excluding Foundation and Labs holdings, of 1,636,316,390 AZTEC. The current staking set is 3,321 attesters, each staking 200,000 AZTEC: 664.2M AZTEC, or 40.6% of sellable supply. Full insider participation adds 23,988 attesters, approximately 4.8B AZTEC.

The model assumes 438,000 checkpoints a year, one per 72-second slot, and a total checkpoint reward of 500 AZTEC. The v5 split is 350 AZTEC for sequencers and 150 for provers; the v6 split is 450 and 50. This produces 219M AZTEC of annual rewards, equivalent to 2.12% of the assumed total supply. Delegator yields are after a 25% operator commission. Real yield is (1 + nominal yield) ÷ (1 + inflation) − 1. Yields assume a checkpoint in every slot; realized yields are lower when slots are missed.

### Yield as locked tokens enter the staking set

When more tokens stake, each attester is picked for committees less often and proposes fewer checkpoints, so the yield falls.

| Insider participation | Attesters | Supply staked | Delegator yield v5 | Delegator yield v6 | Real yield v6 |
| --- | --- | --- | --- | --- | --- |
| 0% | 3,321 | 6.4% | 17.31% | 22.26% | 19.72% |
| 10% | 5,720 | 11.1% | 10.05% | 12.92% | 10.58% |
| 25% | 9,318 | 18.0% | 6.17% | 7.93% | 5.70% |
| 50% | 15,315 | 29.6% | 3.75% | 4.83% | 2.65% |
| 75% | 21,312 | 41.2% | 2.70% | 3.47% | 1.32% |
| 100% | 27,309 | 52.8% | 2.11% | 2.71% | 0.58% |

### Self-run sequencer costs

At $0.014 per AZTEC, the model gives the following minimum stake needed for a self-run operator to break even on v6, including hardware and ETH costs. Each attester requires 200,000 AZTEC.

| Insider participation | Breakeven stake at $150/month | Breakeven stake at $415/month |
| --- | --- | --- |
| 0% | 600,000 AZTEC | 1,200,000 AZTEC |
| 10% | 800,000 AZTEC | 2,200,000 AZTEC |
| 25% | 1,400,000 AZTEC | 3,400,000 AZTEC |
| 50% | 2,000,000 AZTEC | 5,600,000 AZTEC |
| 75% | 2,800,000 AZTEC | 7,800,000 AZTEC |
| 100% | 3,600,000 AZTEC | 10,000,000 AZTEC |

### Maintaining the current delegator yield

Maintaining a 17.3% nominal delegator yield as insiders enter the staking set would require the following sequencer rewards and annual inflation, with the prover pool kept at 10% of the checkpoint reward.

| Insider participation | Sequencer reward per checkpoint | Multiple of v6 reward | Annual inflation | Real yield |
| --- | --- | --- | --- | --- |
| 0% | 350 AZTEC | 0.8× | 1.65% | 15.41% |
| 10% | 603 AZTEC | 1.3× | 2.83% | 14.08% |
| 25% | 982 AZTEC | 2.2× | 4.62% | 12.13% |
| 50% | 1,614 AZTEC | 3.6× | 7.59% | 9.04% |
| 75% | 2,246 AZTEC | 5.0× | 10.56% | 6.10% |
| 100% | 2,878 AZTEC | 6.4× | 13.53% | 3.33% |

At 50% insider participation, maintaining that yield requires 3.6 times the v6 sequencer reward and 7.59% annual inflation. At full participation, it requires 6.4 times the reward and 13.53% annual inflation.

The modelled 13.53% annual issuance is approximately 5.4 times [Celestia’s 2.5% rate introduced by CIP-41](https://github.com/celestiaorg/CIPs/blob/main/cips/cip-041.md) and [NEAR’s 2.5% maximum under its halving upgrade](https://blog.nearone.org/announcement/2025/10/21/enhancing-near-tokenomics.html), and 3.5 times [Solana’s reported 3.82% rate in June 2026](https://forum.solana.com/t/simd-0550-proposal-to-double-disinflation/4874). These comparisons measure gross issuance before fee burns and exclude token unlocks. Celestia’s rate declines annually. Higher issuance increases potential selling pressure as operators sell rewards to cover operating costs.

### Increasing the sequencer reward to 750 AZTEC

Increasing the sequencer reward from 450 to 750 AZTEC, with the same 90/10 split, raises annual inflation from 2.12% to 3.53%. The resulting delegator yields are:

| Insider participation | Delegator yield at 450 AZTEC | Delegator yield at 750 AZTEC |
| --- | --- | --- |
| 0% | 22.26% | 37.09% |
| 25% | 7.93% | 13.22% |
| 50% | 4.83% | 8.04% |
| 75% | 3.47% | 5.78% |
| 100% | 2.71% | 4.51% |

### Operator returns and network liveness

Operators need a dollar return that covers ETH and infrastructure costs. The model gives a 99th-percentile checkpoint posting cost of $2.83. For an operator’s 25% share of a 450 AZTEC sequencer reward to cover that cost, AZTEC would need to be worth approximately $0.025, compared with the model’s assumed price of $0.014.

Lower yields may lead liquid stakers to exit and sell, while reducing the incentive for new buyers to stake. A lower token price reduces the dollar value of operator rewards. Increasing rewards to cover those costs adds issuance and potential selling pressure. The proposal is intended to buy time for network usage and token burns to develop.

### Reduced rewards and locked rewards

The modelling identifies a dilution effect from participation itself: whether or not insiders earn rewards, their stake takes committee seats, so other stakers are selected less often and their yield falls. Setting insider rewards to zero does not remove this effect if locked tokens still enter the staking set. Zero rewards economically discourages locked-token staking but does not prohibit it. Locked holders who run their own sequencers can still participate and dilute other stakers’ yields. Operators of those positions would still incur ETH costs when selected to post checkpoints.

Locking rewards also leaves the committee participation effect in place. Insiders delegate to operators with costs in ETH and dollars; locking the rewards from which those operators are paid would create a further cost-recovery problem.

## Security Considerations

### Committee participation and liveness

Zero rewards does not exclude locked-token positions from committees. Positions that remain in the set but stop proposing or attesting can impair block production. The V6 operator exit mechanism allows delegated positions to be removed through the applicable exit process; removal is not automatic when rewards are set to zero. Activation and operator exits must account for positions that remain eligible for committee selection during the transition.

Self-operated locked positions remain possible. They retain their duties and slashing exposure and continue to dilute other stakers’ selection frequency. Removing checkpoint rewards does not eliminate participation motivated by transaction fees or governance influence.

### Policy calculator

The calculator must distinguish affected insider ATP positions from genesis sequencers, sale participants and other unaffected positions. Verification must cover self-operated and delegated positions, registry classification, and tokens withdrawn and restaked after unlocking.

AZIP-31 governs calculator call safety and fallback behavior. A failed or malformed call pays default rewards; the policy calculator must therefore be tested within its gas limits before activation. Classification uses state at proof submission, as specified in AZIP-31.

### Operator exits

The use of V6 operator exits must preserve token ownership, vesting restrictions and the applicable exit and slashing rules. The reward change does not authorize operators to take ownership of delegated tokens or bypass those restrictions.

V6 allows node operators to exit delegated sequencer positions. Removing checkpoint rewards removes the associated operator commission, giving operators a financial incentive to exit locked-token positions.

## Copyright Waiver

Copyright and related rights waived via [CC0](/LICENSE).
