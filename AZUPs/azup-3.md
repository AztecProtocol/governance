# AZUP-3: Aztec Network v6

> **DRAFT.** The v6 payload has not been deployed. Items marked *TBD* are filled in before the payload is deployed, per the [AZUP process](../azup-process.md) (payload merged here and tagged before deployment).

## Preamble

| `azup` | `title`          | `description`                                                       | `author`                             | `azips-included`                                                                                                                                                                                                | `discussions-to`                                                             | `created`  |
| ------ | ---------------- | ------------------------------------------------------------------- | ------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- | ---------- |
| 3      | Aztec Network v6 | Deploys the v6 rollup and makes it canonical via a governance payload |                                      | [AZIP-22](../AZIPs/azip-22.md), [AZIP-23](../AZIPs/azip-23.md), [AZIP-24](../AZIPs/azip-24.md), [AZIP-25](../AZIPs/azip-25.md), [AZIP-26](../AZIPs/azip-26.md), [AZIP-27](../AZIPs/azip-27.md) | [AZUP-3 proposed inclusions (#60)](https://github.com/AztecProtocol/governance/issues/60) | 2026-09-21 |

## Abstract

AZUP-3 upgrades Aztec Network from the v5 rollup to the v6 rollup. It deploys a new `Rollup` (with its `Inbox`, `Outbox`, `FeeJuicePortal`, `Slasher`, `SlashingProposer` and `RewardBooster`), a new `HonkVerifier` and a new `EscapeHatch`, then executes a governance payload that registers the v6 rollup in the `Registry` and the `GSE` and carries the entry-queue flush incentive across. *TBD: confirm the final action list once the payload is frozen.*

## Motivation

*TBD.* See the included AZIPs. Scheduling per the tracking issue: testnet payload the week of 2026-09-21; mainnet payload after 2026-10-07.

## Specification

### 1. Payload / Action Details

| Item                                     | Value                                                                                                          |
| ---------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| **Payload / Contract / Proposal Address** | *TBD (after deployment)*                                                                                       |
| **Repository**                           | `AztecProtocol/aztec-packages`                                                                                 |
| **Contract / Module**                    | `l1-contracts/src/periphery/V6UpgradePayload.sol` (deploy script: `l1-contracts/script/deploy/DeployRollupForUpgradeV6.s.sol`) |
| **Source pin**                           | *TBD: the release tag the payload and rollup are built from. Copy the payload source into `assets/azup-3/` before deployment.* |
| **Explorer**                             | *TBD*                                                                                                          |

#### Actions

As currently written, `V6UpgradePayload.getActions()` returns, in order:

| # | Target                     | Call                                                        | Effect                                                                                                                   |
| - | -------------------------- | ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| 1 | The payload itself         | `assertWithinExecutionWindow()`                             | Mainnet only: reverts unless execution is on a UK weekday between 08:00 and 17:00 London time. A rejected attempt leaves the proposal executable when the window next opens. |
| 2 | `Registry`                 | `addRollup(v6Rollup)`                                       | Registers the v6 rollup under its version and makes it canonical.                                                        |
| 3 | `GSE`                      | `addRollup(v6Rollup)`                                       | Lets attesters follow the upgrade without withdrawing and re-depositing stake.                                           |
| 4 | v5 `FlushRewarder` `0x5B98cA4dcE7b59CCf241D12f81d3d2eCF14e410e` | `recover(asset, newFlushRewarder, rewardsAvailable())` | Mainnet only: moves the unowed flush-reward balance to a v6 `FlushRewarder` deployed by the payload's constructor.       |

Unlike [AZUP-2](./azup-2.md), the escape hatch is set by the deploy script while the deployer still owns the rollup, so it is not a payload action. The v5 `RewardDistributor` resolves the canonical rollup from the `Registry`, so it is not replaced.

#### Protocol constants fixed by this upgrade

| Constant                          | Value                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| --------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Contract address domain separator | **Must be bumped before the v6 release candidate.** Every protocol version uses a fresh separator so the same contract address cannot exist on two rollup instances (v4: `DOM_SEP__CONTRACT_ADDRESS_V1 = 1788365517`; v5: `DOM_SEP__CONTRACT_ADDRESS_V2 = 4099338721`). v6 uses `DOM_SEP__CONTRACT_ADDRESS_V3 = 993442748` (= `hash_to_u32("az_dom_sep", "contract_address_v3")`). As of 2026-09-21 this is a draft PR against `next` in aztec-packages (#25521), not yet merged; every v6 contract address, including the standard contracts' canonical addresses and the genesis roots, moves with it. *TBD: confirm merged and update if the value changes.* |
| Rollup version                    | *TBD (derived from the deployed configuration)*                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| VK tree root                      | *TBD (from the v6 protocol circuits build)*                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| Protocol contracts hash           | *TBD (from the v6 protocol circuits build)*                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| Default public-setup allowlist    | *TBD: list the contract instances and functions, including which standard `AuthRegistry` instance is canonical (see [AZUP-2](./azup-2.md) open question 1).*                                                                                                                                                                                                                                                                                                                                       |
| Protocol fee margin ([AZIP-23](../AZIPs/azip-23.md)) | *TBD — decision required.* The v6 rollup launches with `protocolFeeMargin = 0` and a placeholder recipient; both are owner-only, so after the deploy script hands ownership to governance they can only be set by a payload. Either this payload sets the recipient and then the margin (in that order), or this AZUP states that the margin ships disabled and a later AZUP activates it.                                                                                                              |

### 2. Sequencer Configuration (for signaling)

Once the payload is deployed, sequencers signal by setting:

```
GOVERNANCE_PROPOSER_PAYLOAD_ADDRESS=<TBD>
```

### 3. Testnet (Sepolia)

*TBD after the testnet deployment.* On Sepolia the execution-window action and the flush-rewarder migration are omitted (no window enforcement; no flush rewarder to migrate).

## Impact Evaluation

*TBD.*

## Security & Audits

*TBD.* Note for reviewers: the payload's execution window uses on-chain weekday/BST arithmetic; it should be covered by a unit test before deployment, since the deploy script's fork simulation is the only thing that currently exercises the payload.

## Open Questions and Feedback

1. The contract address domain separator bump (V3 = 993442748, aztec-packages #25521) is a draft PR and must merge before the v6 release candidate is cut.
2. Does this AZUP activate the protocol fee margin ([AZIP-23](../AZIPs/azip-23.md)) or only ship the mechanism?
3. Which standard `AuthRegistry` instance is canonical for the public-setup allowlist?

## Copyright Waiver

Copyright and related rights waived via [CC0](/LICENSE).
