# AZUP-3: Aztec Network v6

## Preamble

| `azup` | `title`          | `description`                                                         | `author` | `azips-included`                                                                                                                                                                                                                                                  | `discussions-to`                                                                          | `created`  |
| ------ | ---------------- | --------------------------------------------------------------------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- | ---------- |
| 3      | Aztec Network v6 | Deploys the v6 rollup and makes it canonical via a governance payload |          | [AZIP-22](../AZIPs/azip-22.md), [AZIP-23](../AZIPs/azip-23.md), [AZIP-24](../AZIPs/azip-24.md), [AZIP-25](../AZIPs/azip-25.md), [AZIP-26](../AZIPs/azip-26.md), [AZIP-27](../AZIPs/azip-27.md), [AZIP-28](https://github.com/AztecProtocol/governance/pull/68), [AZIP-29](https://github.com/AztecProtocol/governance/pull/70), [AZIP-30](https://github.com/AztecProtocol/governance/pull/74), [AZIP-31](https://github.com/AztecProtocol/governance/pull/77), [AZIP-33](https://github.com/AztecProtocol/governance/pull/79), [AZIP-34](https://github.com/AztecProtocol/governance/pull/81) | [AZUP-3 proposed inclusions (#60)](https://github.com/AztecProtocol/governance/issues/60) | 2026-09-21 |

## Abstract

This upgrade package moves Aztec Network from the v5 rollup to a new v6 rollup that implements ten AZIPs. The v6 rollup is deployed ahead of the proposal, owned by governance and inactive. The payload then reserves 1,800,000 AZTEC for v5's remaining payouts, lowers v5's checkpoint reward from 500 to 50 AZTEC, installs v6's escape hatch, and registers v6 in the `Registry` and the `GSE`. It also raises the GSE's proof-of-possession gas cap from 250,000 to 300,000. Registration makes v6 canonical, and stake that follows the latest rollup moves to v6 without being withdrawn.

## Motivation

**Faster L1-to-L2 messaging.** Today an L1-to-L2 message waits for the Inbox tree to seal and then for a two-checkpoint lag, so it takes 24 to 108 seconds to reach L2. [AZIP-22](../AZIPs/azip-22.md) streams messages into blocks as soon as nodes see them on L1, bringing that down to about 12 to 30 seconds. Every deposit, bridge and portal flow benefits.

**A way out for staking providers.** A staking provider operates the validator, but only the delegator's withdrawer can start an exit. A provider that no longer wants to run sequencers cannot end the arrangement: if it simply stops, its delegators are slashed for inactivity. [AZIP-27](../AZIPs/azip-27.md) lets the provider exit the positions it operates, while the payout still goes to the delegator. A shared rate limit stops providers from using exits to swing a governance vote.

**Protocol fee capture.** Fees are priced at exactly the cost of running the network, so usage contributes nothing towards the block rewards that token holders fund through supply growth. [AZIP-23](../AZIPs/azip-23.md) adds a governance-set margin on top of cost and a governance-set recipient for it, so that usage can start to offset those rewards. The margin launches at zero, and governance can raise it in rate-limited steps.

**Ready before Glamsterdam.** Ethereum's Glamsterdam fork makes the L1 transactions behind checkpoint proposals and epoch proofs materially more expensive. [AZIP-28](https://github.com/AztecProtocol/governance/pull/68) raises the fee model's L1 gas constants now, so that fees cover sequencer and prover L1 costs from the moment the fork activates, with no further governance action at the fork.

**Reward policy without a redeploy.** Every proposer earns the same sequencer reward, and changing how rewards are computed means deploying a new rollup. [AZIP-31](https://github.com/AztecProtocol/governance/pull/77) lets governance point the rollup at a separate reward calculator contract instead, so a future reward policy can ship without a rollup upgrade. A calculator that fails or misbehaves falls back to the default reward and can never block a proof.

**Valid validator keys that fit the gas cap.** The GSE checks each new validator's BLS key within a 250,000 gas cap, and the cost of that check varies by key. Osaka made the check more expensive, and the cap was not raised with it, so about 1 in 28,559 honestly generated keys is now rejected at registration, against about 1 in 4.2 million before. [AZIP-33](https://github.com/AztecProtocol/governance/pull/79) raises the cap to 300,000, which brings the rate back to about 1 in 2.5 million.

**Keeping v5 alive during migration.** Once v6 is canonical, v5 can no longer draw rewards from the RewardDistributor. Without rewards, provers have little reason to keep proving v5, and users still migrating could be left on a chain that stops finalizing. [AZIP-34](https://github.com/AztecProtocol/governance/pull/81) earmarks 1,800,000 AZTEC for v5 and lowers its checkpoint reward to 50 AZTEC. At 1,200 checkpoints a day, that funds v5 for 30 days.

## Specification

### 1. Included AZIPs

| AZIP | Change in v6 |
| --- | --- |
| [22](../AZIPs/azip-22.md) Fast Inbox | L1-to-L2 messages stream into L2 blocks as nodes observe them, instead of waiting for a two-checkpoint lag. |
| [23](../AZIPs/azip-23.md) Protocol Fee Margin | A governance-set margin on the mana base fee, paid to a governance-set recipient. Launches at zero. |
| [24](../AZIPs/azip-24.md) First Prover Attribution | The rollup records which prover first proved each checkpoint. |
| [25](../AZIPs/azip-25.md) Full Epoch Activity Score | A prover's activity score only increases on a full-epoch proof. |
| [26](../AZIPs/azip-26.md) Transaction Effects Tree | Each block header commits to a tree of its transactions' effects. |
| [27](../AZIPs/azip-27.md) Rate-limited Provider Exits | Staking providers can exit positions they operate, up to 5% of the validator set per 7 days. |
| [28](https://github.com/AztecProtocol/governance/pull/68) Glamsterdam Gas Constants | L1 gas per checkpoint rises from 300,000 to 500,000, and per epoch proof from 3,600,000 to 4,000,000. |
| [29](https://github.com/AztecProtocol/governance/pull/70) Protocol Nullifier Refinement | The protocol nullifier is derived from `(origin, chain_id, version, salt)`. |
| [30](https://github.com/AztecProtocol/governance/pull/74) 90% Sequencer Reward Share | The sequencer share of the 500 AZTEC checkpoint reward rises from 70% to 90%. |
| [31](https://github.com/AztecProtocol/governance/pull/77) Pluggable Sequencer Reward Calculator | The rollup can call a governance-set contract to set each proposer's sequencer reward. v6 launches with none set, so every proposer earns the default. |
| [33](https://github.com/AztecProtocol/governance/pull/79) Proof-of-Possession Gas Cap | The payload raises the GSE's proof-of-possession gas cap from 250,000 to 300,000. No contract code changes. |
| [34](https://github.com/AztecProtocol/governance/pull/81) Sustain v5 After v6 | The payload earmarks 1,800,000 AZTEC for v5 and cuts its checkpoint reward from 500 to 50 AZTEC, so v5 stays sequenced and proven for 30 days. |

### 2. Payload / Action Details

The actions execute in this order, in one transaction.

**Action 1: Confirm v5 is still canonical**

| Item         | Value                                                                                            |
| ------------ | ------------------------------------------------------------------------------------------------ |
| **Contract** | Payload                                                                                          |
| **Function** | `assertPredecessorIsCanonical()`                                                                 |
| **Effect**   | Reverts unless v5 is still canonical, so the payload cannot execute after any other upgrade.     |

**Action 2: Enforce the execution window**

| Item         | Value                                                                                  |
| ------------ | -------------------------------------------------------------------------------------- |
| **Contract** | Payload                                                                                |
| **Function** | `assertWithinExecutionWindow()`                                                        |
| **Effect**   | Reverts unless execution falls on a UK weekday between 08:00 and 17:00 London time.    |

**Action 3: Reserve rewards for v5 ([AZIP-34](https://github.com/AztecProtocol/governance/pull/81))**

| Item         | Value                                                                                                                   |
| ------------ | ----------------------------------------------------------------------------------------------------------------------- |
| **Contract** | RewardDistributor, then Payload                                                                                          |
| **Function** | `recoverFrom(v5, payload, amount)`, then `forwardEarmark()`                                                              |
| **Effect**   | Reserves 1,800,000 AZTEC in the RewardDistributor for v5, so v5 can still pay out rewards after it stops being canonical. |

**Action 4: Lower v5's checkpoint reward ([AZIP-34](https://github.com/AztecProtocol/governance/pull/81))**

| Item         | Value                                                                                   |
| ------------ | --------------------------------------------------------------------------------------- |
| **Contract** | Rollup v5                                                                               |
| **Function** | `setRewardConfig({ sequencerBps: 7000, checkpointReward: 50e18 })`                       |
| **Effect**   | Lowers v5's checkpoint reward from 500 to 50 AZTEC for the checkpoints it settles after the upgrade. The 70/30 split is unchanged. |

**Action 5: Install the v6 escape hatch**

| Item         | Value                                                |
| ------------ | ---------------------------------------------------- |
| **Contract** | Rollup v6                                            |
| **Function** | `setEscapeHatch(escapeHatch)`                        |
| **Effect**   | Installs v6's escape hatch. It can only be set once. |

**Action 6: Make v6 canonical**

| Item         | Value                                                                               |
| ------------ | ----------------------------------------------------------------------------------- |
| **Contract** | Registry                                                                            |
| **Function** | `addRollup(v6)`                                                                     |
| **Effect**   | Registers v6 and makes it the canonical rollup. The RewardDistributor follows it.   |

**Action 7: Move stake to v6**

| Item         | Value                                                                                                                    |
| ------------ | ------------------------------------------------------------------------------------------------------------------------ |
| **Contract** | GSE                                                                                                                      |
| **Function** | `addRollup(v6)`                                                                                                          |
| **Effect**   | Stake that follows the latest rollup moves to v6 without being withdrawn. Stake deposited directly into v5 stays there.  |

**Action 8: Migrate the entry-queue flush incentive**

| Item         | Value                                                                                              |
| ------------ | -------------------------------------------------------------------------------------------------- |
| **Contract** | FlushRewarder v5                                                                                   |
| **Function** | `recover(asset, newFlushRewarder, rewardsAvailable())`                                             |
| **Effect**   | Moves the unowed flush-reward balance to v6's FlushRewarder. Rewards already owed stay claimable.  |

**Action 9: Raise the proof-of-possession gas cap**

| Item         | Value                                                                                                                         |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------- |
| **Contract** | GSE                                                                                                                           |
| **Function** | `setProofOfPossessionGasLimit(300_000)`                                                                                       |
| **Effect**   | Raises the gas cap for verifying a new validator's BLS proof of possession from 250,000 to 300,000, for every rollup on the GSE. |

The payload does not change the protocol fee margin (AZIP-23), which launches at zero and needs a separate proposal to change. v6 is deployed with no sequencer reward calculator (AZIP-31), and any reward policy that uses one needs its own AZIP and AZUP. The payload does not renounce ownership of v5.

## Impact Evaluation

**Sequencers** — Must run v6 software. Stake that follows the latest rollup moves to v6 at execution, and its first v6 duties begin two to three epochs later. The default sequencer reward rises from 350 to 450 AZTEC per checkpoint, and every proposer earns it until governance sets a reward calculator. Valid new BLS keys are far less likely to be rejected at registration. Sequencers whose stake stays on v5 earn 35 AZTEC per checkpoint there, from the earmark, until it runs out.

**Provers** — The block-reward prover pool falls from 150 to 50 AZTEC per checkpoint; fee-based prover revenue is unchanged. Activity scores only increase on full-epoch proofs. v5 provers earn 15 AZTEC per checkpoint from the earmark for about 30 days.

**Tokenholders** — Emissions are unchanged at 500 AZTEC per checkpoint, with more of it going to sequencers. Governance gains a fee margin and a sequencer reward calculator, both to set in later proposals. Staking providers can exit delegated positions, within the rate limit.

**App Developers & Infrastructure Providers** — v6 is a new rollup: contracts must be recompiled, and class ids and addresses change. L1-to-L2 messages arrive in seconds rather than minutes, and contracts can prove transaction effects against a block header. L2 fees rise slightly with the Glamsterdam gas constants.

## Security & Audits

**Only the approved transition**: The payload checks at execution that v5 is still canonical, so it cannot demote a rollup registered after it was deployed.

**Atomicity**: `Governance.execute` requires every action to succeed within one transaction. A failed check leaves nothing changed.

**Ordering**: Action 3 must run before Action 6, because once v6 is registered, v5 can no longer draw on the RewardDistributor's pool. Action 4 also runs before it, so the lower reward applies to everything v5 settles after the upgrade.

**Testing**: The payload has unit tests for its actions, constructor and execution window, a scenario test that executes it through governance and checks atomicity, and a fork simulation of the full lifecycle.

**Audits**: *TBD.*

## Copyright Waiver

Copyright and related rights waived via [CC0](/LICENSE).
