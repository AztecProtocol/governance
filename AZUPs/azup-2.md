# AZUP-2: Aztec Network v5

## Preamble

| `azup` | `title`          | `description`                                                                                       | `author`                             | `azips-included`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              | `discussions-to`                                                        | `created`  |
| ------ | ---------------- | --------------------------------------------------------------------------------------------------- | ------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- | ---------- |
| 2      | Aztec Network v5 | Deploys the v5 rollup and makes it canonical, migrating rewards, staking and the escape hatch to it |                                      | [AZIP-2](../AZIPs/azip-2.md), [AZIP-5](../AZIPs/azip-5.md), [AZIP-6](../AZIPs/azip-6-pipelining.md), [AZIP-7](../AZIPs/azip-7-update_slashing.md), [AZIP-8](../AZIPs/azip-8.md), [AZIP-9](../AZIPs/azip-9.md), [AZIP-10](../AZIPs/azip-10.md), [AZIP-12](../AZIPs/azip-12.md), [AZIP-13](../AZIPs/azip-13.md), [AZIP-14](../AZIPs/azip-14.md), [AZIP-16](../AZIPs/azip-16.md), [AZIP-17](../AZIPs/azip-17.md), [AZIP-19](../AZIPs/azip-19.md) | [Forum: AZUP-2 is Ready for Proposal](https://forum.aztec.network/t/azup-2-is-ready-for-proposal/8605) | 2026-06-29 |

> This AZUP is filed retroactively. The upgrade was announced on the forum on 2026-06-29 (by Amin Sammara), proposed on-chain on 2026-07-02 and executed on 2026-07-14, but no `azup-2.md` was merged into this repository as the [AZUP process](../azup-process.md) requires. Everything below was read back from the deployed contracts and from the verified source on Sourcify, not copied from the announcement; where a value could not be independently verified it is marked as such.
>
> **How this record was reconciled.** Addresses were read from Ethereum mainnet and Sepolia over JSON-RPC on 2026-09-21, starting from the `Governance` contract's proposal id 4, unwrapping its `GSEPayload` to the `V5UpgradePayload`, and following that payload's immutables and the rollup's getters outward; each sub-contract's pointer back to the rollup was checked. The getter names used for those reads (`NEW_ROLLUP`, `ESCAPE_HATCH`, `NEW_FLUSH_REWARDER`, …) were taken from `l1-contracts/src/periphery/V5UpgradePayload.sol` at tag **`v5.0.0-rc.2`** of `AztecProtocol/aztec-packages`, the release tag current when the contracts were deployed (2026-06-30). That tag was then confirmed as the deployed source by comparing every file in each contract's Sourcify verification against the tag's tree (all identical). The same files are unchanged at tags `v5.0.0` and `v5.0.1` and at the head of the `v5` release branch (`5.2.0`), so any of those refs reproduces the deployed code; the working branch `v5-next` also matches but is not a release ref. Transaction hashes and timestamps come from Sourcify's deployment records and from the `ProposalExecuted` event logs.

## Abstract

AZUP-2 upgrades Aztec Network from the v4 rollup to the v5 rollup. It deploys a new `Rollup` (with its `Inbox`, `Outbox`, `FeeJuicePortal`, `Slasher`, `SlashingProposer` and `RewardBooster`), a new `HonkVerifier`, a new `EscapeHatch`, a new `RewardDistributor` and a replacement `FlushRewarder`, then executes a single governance payload that registers the v5 rollup in the `Registry` and the `GSE`, points the `Registry` at the new reward distributor, drains the v4 distributor's balance into it, activates the escape hatch on the v5 rollup, and carries the entry-queue flush incentive across. The thirteen AZIPs listed in the preamble are the protocol changes shipped with v5.

## Motivation

See the individual AZIPs and the forum announcement linked above. Several of the included AZIPs are not expressible as a parameter change on the v4 rollup and require a new rollup instance (new protocol circuits and verifier under AZIP-13 and AZIP-17, a reduced protocol contract set under AZIP-12, new validator key material under AZIP-8 and AZIP-10). Existing stake follows the upgrade without withdrawing: `GSE.addRollup` lets attesters delegated to the canonical rollup move to v5.

## Specification

### 1. Payload / Action Details

| Item                                     | Value                                                                                                                                                                                |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Payload / Contract / Proposal Address** | `0x1bBde48410bF7Ad05208cD77dE2bFb0e8F8803D8` (`V5UpgradePayload`; this is the address sequencers signaled for)                                                                          |
| **Governance proposal**                  | On-chain proposal id **4** (0-indexed `proposalId`; unrelated to AZUP numbering) on `Governance` `0x1102471eb3378fee427121c9efcea452e4b6b75e`, whose stored payload is the `GSEPayload` wrapper `0x1744be5cf3f314bfb2999db8acec1748916e74b5` created by `GovernanceProposer.submitRoundWinner` around the address above |
| **Repository**                           | `AztecProtocol/aztec-packages`                                                                                                                                                       |
| **Contract / Module**                    | `l1-contracts/src/periphery/V5UpgradePayload.sol` (deploy script: `l1-contracts/script/deploy/DeployRollupForUpgradeV5.s.sol`)                                                       |
| **Source pin**                           | Tag `v5.0.0-rc.2`. Every source file in the Sourcify verification of the payload (67 files), the rollup (80 files) and the verifier is byte-identical to that tag; the same files are unchanged at `v5.0.0`, `v5.0.1` and the head of the `v5` branch. Copies of the payload source and of the deploy script that holds the rollup configuration table are in [`assets/azup-2/V5UpgradePayload.sol`](../assets/azup-2/V5UpgradePayload.sol) and [`assets/azup-2/DeployRollupForUpgradeV5.s.sol`](../assets/azup-2/DeployRollupForUpgradeV5.s.sol). |
| **Explorer**                             | [Payload on Etherscan](https://etherscan.io/address/0x1bBde48410bF7Ad05208cD77dE2bFb0e8F8803D8#code) · [Sourcify (exact match)](https://repo.sourcify.dev/1/0x1bBde48410bF7Ad05208cD77dE2bFb0e8F8803D8) |

#### Actions

`getActions()` returns six actions on mainnet (the sixth is only included when there is a flush rewarder to migrate). Governance executes them in order, atomically.

| # | Target                                                       | Call                                                                                      | Effect                                                                                                         |
| - | ------------------------------------------------------------ | ----------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| 1 | v4 `RewardDistributor` `0x3D6A1B00C830C5f278FC5dFb3f6Ff0b74Db6dfe0` | `recover(asset, newDistributor, balanceOf(oldDistributor))` (legacy selector)              | Moves the v4 distributor's entire fee-asset balance to the v5 distributor. Amount read at execution time.      |
| 2 | `Registry` `0x35b22e09ee0390539439e24f06da43d83f90e298`      | `addRollup(0x91fF8bbD8Ebb07893010D50A48A1609e5EBd8E34)`                                    | Registers the v5 rollup as version `4248422647` and makes it canonical.                                        |
| 3 | `Registry`                                                   | `updateRewardDistributor(0x555bAAc4757A89f1CE0c84fA35afE9dD7aa8E1d3)`                     | Points the registry at the v5 reward distributor.                                                              |
| 4 | `GSE` `0xa92ecfd0e70c9cd5e5cd76c50af0f7da93567a4f`           | `addRollup(0x91fF8bbD8Ebb07893010D50A48A1609e5EBd8E34)`                                    | Lets attesters follow the upgrade without withdrawing and re-depositing stake.                                 |
| 5 | v5 `Rollup` `0x91fF8bbD8Ebb07893010D50A48A1609e5EBd8E34`     | `setEscapeHatch(0xF459348962F5eA3A9A101826B03A2CE1F459E51A)`                              | One-shot, owner-only: activates the escape hatch on the v5 rollup.                                             |
| 6 | v4 `FlushRewarder` `0xf1AcfB0C6ADd7104e700b8FAd3Ea025dbB041F34` | `recover(asset, newFlushRewarder, rewardsAvailable())`                                 | Moves the unowed flush-reward balance to the v5 `FlushRewarder`; rewards already accrued to flushers stay claimable on the old one. |

#### Governance record (Ethereum mainnet)

| Step                            | When (UTC)          | Block      | Transaction                                                          |
| ------------------------------- | ------------------- | ---------- | -------------------------------------------------------------------- |
| Contracts deployed              | 2026-06-30 07:08:47 | 25,428,902 | Rollup `0x096bfc58c8dc953727c8f793343835209c4b82676f78898d04478d8ef4dcd041`, payload `0x101746c82e0097773889a8ce68f195daf5a576bbd63415395fbddf5205212478`, verifier `0xb10e69a4c124fdad2046b2f386610737b567781d4fe711fa728dd0184bd77326`, escape hatch `0xc109a3626618339abef67e448bd31ead21cfd319b0946b94cd1f77e50160e457`, reward distributor `0x209f495e41562e9fdbc23afe2b0b670fc1747f552f6567c21d1437327e2248ee` (deployer `0x47C47232F55CeC65FDfD027ec0799B4B03913444`) |
| Proposal created (`submitRoundWinner`) | 2026-07-02 20:18:11 | 25,447,166 | `0x452b22d4365735d5633e6e608d1c7b17840d44e417fe855c7ab71eb97f4a00e6`  |
| Proposal executed (`execute(4)`) | 2026-07-14 20:22:47 | 25,533,241 | `0xff2db4e4bba583f2451478bfe4703e16afc79f0b463fb60615ebe3494142437b`  |

#### Contracts deployed by this upgrade (Ethereum mainnet)

Every address below was read from the chain (from the payload's immutables and the rollup's getters), each contract's back-pointer to the rollup was checked, and every contract is an exact match on Sourcify (solc `0.8.30`). Contracts marked *ctor* were created inside another contract's constructor in the same transaction and so have no deployment transaction of their own.

| Contract                                 | Address                                      | Notes                                                                                                   |
| ---------------------------------------- | -------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `V5UpgradePayload`                       | `0x1bBde48410bF7Ad05208cD77dE2bFb0e8F8803D8` | The payload                                                                                             |
| `GSEPayload` (wrapper)                   | `0x1744be5cf3f314bfb2999db8acec1748916e74b5` | Created by `GovernanceProposer`; what `Governance` stores for proposal id 4                               |
| `Rollup` (v5)                            | `0x91fF8bbD8Ebb07893010D50A48A1609e5EBd8E34` | Version `4248422647`; owner is `Governance`                                                             |
| `HonkVerifier`                           | `0x098f47c00F4df22a8030746Eb11378236C24b4bC` | Epoch proof verifier                                                                                    |
| `Inbox`                                  | `0x7d4Ef0676c2032bbCC09227501D34d86641ab8cA` | *ctor*; `ROLLUP` and `VERSION` point at the v5 rollup                                                    |
| `Outbox`                                 | `0x5B062aB5fD3A66BC7e73b04CeD38587673b6A2D7` | *ctor*; `ROLLUP` and `VERSION` point at the v5 rollup                                                    |
| `FeeJuicePortal`                         | `0xaf73Dd51D1eb8a079BB097f39c832cDD00ac691c` | *ctor*                                                                                                   |
| `Slasher`                                | `0xCD6855470A01aBcd989126A1183Fb50673952548` | *ctor*; vetoer `0xBbB4aF368d02827945748b28CD4b2D42e4A37480`                                             |
| `SlashingProposer`                       | `0x8A36b8F2Ca71D8d8Bd98e03Ebf8B4D0939Daf0bA` | *ctor*; `INSTANCE` is the v5 rollup                                                                     |
| `SlashPayloadCloneable` (implementation) | `0x57576AbA1932df7Cc30F971ACC9d4Fc6E86B6e87` | *ctor*                                                                                                   |
| `RewardBooster`                          | `0x4490cAb7Ce3499353E1b0090b9e530c1AD03B551` | *ctor*                                                                                                   |
| `EscapeHatch`                            | `0xF459348962F5eA3A9A101826B03A2CE1F459E51A` | `getRollup()` is the v5 rollup; bond token is the staking asset                                          |
| `RewardDistributor` (v5)                 | `0x555bAAc4757A89f1CE0c84fA35afE9dD7aa8E1d3` | Replaces `0x3D6A1B00C830C5f278FC5dFb3f6Ff0b74Db6dfe0`                                                    |
| `FlushRewarder` (v5)                     | `0x5B98cA4dcE7b59CCf241D12f81d3d2eCF14e410e` | *ctor* (inside the payload); replaces `0xf1AcfB0C6ADd7104e700b8FAd3Ea025dbB041F34`, same asset and rate (100 tokens per insertion), owned by `Governance` |

Inherited, not deployed by this upgrade: `Registry` `0x35b22e09ee0390539439e24f06da43d83f90e298`, `Governance` `0x1102471eb3378fee427121c9efcea452e4b6b75e`, `GovernanceProposer` `0x06ef1dcf87e419c48b94a331b252819fadbd63ef`, `GSE` `0xa92ecfd0e70c9cd5e5cd76c50af0f7da93567a4f`, fee/staking asset `0xa27ec0006e59f245217ff08cd52a7e8b169e62d2`. The v4 rollup `0xAe2001f7e21d5EcABf6234E9FDd1E76F50F74962` (version `2934756905`) remains registered as an earlier version; its ownership was renounced by [AZUP-1](./azup-1.md).

#### Protocol constants fixed by this upgrade

| Constant                          | Value                                                                                                                                                                               |
| --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Rollup version                    | `4248422647`                                                                                                                                                                        |
| VK tree root                      | `0x2b3b6ea4412b9c8f6457a37f91a2870306f8641e07e16a49b68bda6f8bc02892`                                                                                                                |
| Protocol contracts hash           | `0x2c075866eafc88a1f6f9addc7e337c6e64e45d1cb7fd7c0d612ebcec72aab2ca`                                                                                                                |
| Genesis archive root              | `0x177a4955b31ecaafad999753938a44e526b54c5ba5d536688227f85f15cfbdf5` (`archiveAt(0)`; identical on Sepolia)                                                                          |
| Contract address domain separator | `DOM_SEP__CONTRACT_ADDRESS_V2 = 4099338721` (= `hash_to_u32("az_dom_sep", "contract_address_v2")`), up from v4's `DOM_SEP__CONTRACT_ADDRESS_V1 = 1788365517`. Every protocol version uses a fresh separator so that the same contract address cannot exist on two rollup instances. |
| Protocol contract set ([AZIP-12](../AZIPs/azip-12.md)) | `ContractClassRegistry` = `0x…01`, `ContractInstanceRegistry` = `0x…02`, `FeeJuice` = `0x…03`                                                                            |
| Default public-setup allowlist    | `AuthRegistry._set_authorized`, `AuthRegistry.set_authorized` and `FeeJuice._increase_public_balance` (node default, `allowed_public_setup.ts`). `AuthRegistry` is a standard contract, not part of the protocol. The canonical instance is `0x1e8e7e73c592a1b1c9199b4b655ddc7a16fa8a8488df595610b71d3dc1cc666c` (pinned by release `5.0.1` onward, and what nodes reference). An earlier instance, `0x00b6c13d47a52717bc54afe32169319be75fa5874cf6da3ba5691b0d5800e2fb` (pinned by release `5.0.0`), also exists on mainnet L2 and is superseded. |
| Sequencer reward share            | 7000 bps of a 500-token checkpoint reward (`getRewardConfig()`)                                                                                                                    |

#### Rollup configuration

The rollup, escape hatch and slasher parameters below were read from the deployed mainnet contracts on 2026-09-21 and compared with the expected-configuration table in `DeployRollupForUpgradeV5.s.sol` at tag `v5.0.0-rc.2` (the check the script's own `validate()` performs at deploy time). Every value matches. The entry-queue configuration was decoded from the rollup's packed staking storage slot. Sepolia was checked the same way against the script's Sepolia overrides (listed where they differ) and also matches.

| Parameter                          | Mainnet                              | Sepolia (where different) |
| ---------------------------------- | ------------------------------------ | ------------------------- |
| Slot duration / epoch duration     | 72 s / 32 slots                      |                           |
| Target committee size              | 48                                   |                           |
| Lag in epochs: validator set / RANDAO | 2 / 1                             |                           |
| Inbox lag                          | 2 (AZIP-6)                           |                           |
| Proof submission epochs            | 1                                    |                           |
| Activation / ejection threshold (GSE) | 200,000 / 100,000 tokens          |                           |
| Local ejection threshold           | 190,000 tokens                       | 199,000 tokens            |
| Exit delay                         | 345,600 s (4 days)                   | 172,800 s (2 days)        |
| Mana target                        | 75,000,000                           |                           |
| Proving cost per mana              | 12,500,000 (AZIP-16)                 |                           |
| Initial ETH per fee asset (E12)    | 9,512,195 at deploy; oracle-updated since (5,858,348 on 2026-09-21) |             |
| Entry queue: bootstrap set size / bootstrap flush / normal flush min / quotient / max flush | 500 / 4 / 1 / 400 / 4 |    |
| Sequencer share / checkpoint reward | 7000 bps / 500 tokens               |                           |
| Reward boost (increment, maxScore, a, minimum, k) | 101,400 / 367,500 / 250,000 / 10,000 / 1,000,000 (AZIP-5) |  |
| Slashing: round size / quorum      | 4 epochs (128 slots) / 65            |                           |
| Slashing: lifetime / execution delay / offset (rounds) | 34 / 28 / 2      | 5 / 2 / 2                 |
| Slashing: disable duration         | 259,200 s (3 days)                   | 432,000 s (5 days)        |
| Slashing vetoer                    | `0xBbB4aF368d02827945748b28CD4b2D42e4A37480` | `0xdfe19Da6a717b7088621d8bBB66be59F2d78e924` |
| Slash amounts small / medium / large | 2,000 / 5,000 / 5,000 tokens (AZIP-16) | 100,000 / 250,000 / 250,000 tokens |
| Escape hatch: bond / withdrawal tax / failed-hatch punishment | 332,000,000 / 1,660,000 / 9,600,000 tokens |  |
| Escape hatch: frequency / active duration / lag in hatches | 112 epochs / 2 epochs / 1 |               |
| Escape hatch: proposing exit delay | 30 days                              |                           |

### 2. Sequencer Configuration (for signaling)

Signaling for this proposal is closed (it has executed). For the record, sequencers signaled by setting:

```
GOVERNANCE_PROPOSER_PAYLOAD_ADDRESS=0x1bBde48410bF7Ad05208cD77dE2bFb0e8F8803D8
```

### 3. Testnet (Sepolia)

The same payload was executed on Sepolia as on-chain proposal id **5** on `0xCAf7447721447B22Cd0076aC7C63877c3AFD329F` (executed 2026-07-13 12:53:00 UTC in tx `0xa5fea6306e52e2b69d7b413b89aba0bf83f900cac1cd50d30da79a7f704ab043`), after two earlier v5 release-candidate rollups had been registered by proposal ids 3 and 4. Addresses were read from the chain; the Sepolia payloads are not verified on Sourcify.

| Contract                 | Address                                      |
| ------------------------ | -------------------------------------------- |
| `V5UpgradePayload`       | `0x6c5094dd7f696a213ba8a1e46801627d5e9fe328` |
| `Rollup` (v5)            | `0xD73A91bdcF6891C7642F3e460036e1ef2CC23178` (version `1821665230`) |
| `HonkVerifier`           | `0x31F98dfC544E52e4170c0Dc64098049651db48C1` |
| `Inbox`                  | `0x3047dBF2b7dd9f58AC41113525480F94745a4f7C` |
| `Outbox`                 | `0x905f80009bBef9d9426675B45009922971eD42fF` |
| `FeeJuicePortal`         | `0xb4A9F8EAdC8CA944729D61E59A9f491fAFf237A3` |
| `Slasher`                | `0xBFa3625CfC7cdDAbF29961e12C4399c5bd8D8763` |
| `SlashingProposer`       | `0x504331248Eb1359C247a0e6895fFfeA70ecdb9a8` |
| `SlashPayloadCloneable`  | `0x0f7aC5F5087bD7CA05957321c75CdF9bD70D9b2E` |
| `RewardBooster`          | `0xdFA442Dd70e654455C3D83d3fE1034751e15385e` |
| `EscapeHatch`            | `0x76eA4430f967888D09034059d011A80Aa0D8E47E` |
| `RewardDistributor`      | `0x83B2A93EF343cAb7Be9D8Bba7317f314975e5CB0` |

Sepolia has no flush rewarder, so the payload's sixth action is omitted there.

## Impact Evaluation

**Sequencers** — Stake delegated to the canonical rollup follows the upgrade via `GSE.addRollup`; no withdrawal is needed. Slashing rules change per [AZIP-7](../AZIPs/azip-7-update_slashing.md) and [AZIP-16](../AZIPs/azip-16.md); new key material is required per [AZIP-8](../AZIPs/azip-8.md) and [AZIP-10](../AZIPs/azip-10.md). Node operators must run v5 node software.

**Provers** — New protocol circuits and verifier ([AZIP-13](../AZIPs/azip-13.md), [AZIP-17](../AZIPs/azip-17.md)); reward accounting changes per [AZIP-5](../AZIPs/azip-5.md).

**Tokenholders** — Rewards accrue through the v5 `RewardDistributor`; the v4 distributor's balance was moved across at execution.

**App developers and infrastructure** — Contract addresses are derived with a new domain separator, so v4 addresses do not carry over. The protocol contract set is reduced and compacted per [AZIP-12](../AZIPs/azip-12.md). Message passing uses the new `Inbox`/`Outbox` scoped to rollup version `4248422647`.

## Security & Audits

- Every contract listed for mainnet is an exact-match verification on Sourcify, and its verified source is byte-identical to the `v5.0.0-rc.2` tag of `AztecProtocol/aztec-packages`.
- The payload's constructor checks, at deploy time, that the escape hatch points at the new rollup and that the rollup's hatch slot is empty, because `setEscapeHatch` is one-shot and a failed execution cannot be retried.
- The balance drain (action 1) and the flush-reward migration (action 6) read amounts at execution time, not at proposal time.
- Audit references for the v5 contracts and circuits: *to be added by Core Contributors* (not stated in the forum announcement).

## Open Questions and Feedback

1. This AZUP was filed after execution. The process requires the payload to be merged and tagged here *before* deployment; no tag was created for AZUP-2 (this repository has no tags). Proposal ids 0–2 on mainnet Governance also predate the AZUP process and have no AZUP.

## Copyright Waiver

Copyright and related rights waived via [CC0](/LICENSE).
