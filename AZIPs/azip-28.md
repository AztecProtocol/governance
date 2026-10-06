# AZIP-28: Update L1 Gas Constants for Glamsterdam

## Preamble

| `azip` | `title` | `description` | `author` | `discussions-to` | `status` | `category` | `created` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 28 | Update L1 Gas Constants for Glamsterdam | Updates fee-model gas constants for checkpoint proposals and epoch proofs ahead of Ethereum's Glamsterdam fork. | Santiago Palladino (@spalladino, santiago@aztec-labs.com) | https://github.com/AztecProtocol/governance/discussions/69 | Draft | Economics | 2026-09-18 |

## Abstract

This proposal updates the fixed L1 gas estimates used by Aztec's fee model to account for Ethereum's Glamsterdam fork. It increases the gas attributed to proposing a checkpoint from 300,000 to 520,000 and decreases the gas attributed to verifying an epoch from 3,600,000 to 2,500,000. Both values come from v6 transactions measured on Sepolia after Glamsterdam activated there on 2026-10-06. Deploying the final values with v6 may cause higher pre-fork proposal fees, but avoids underpayment and an additional governance-controlled update when the fork activates on mainnet.

## Impacted Stakeholders

**Users.** The checkpoint-proposal estimate increases and the epoch-verification estimate decreases. The net effect on the L1-cost component of the mana base fee depends on the L1 gas price and on how these costs are amortized over mana. Before Glamsterdam activates on mainnet, the proposal component is higher than the L1 work it pays for.

**Sequencers.** The checkpoint-proposal estimate used to calculate the sequencer cost component increases. This reduces the risk that sequencers under-recover their L1 publication costs after Glamsterdam.

**Provers.** The epoch-verification estimate used to calculate the prover cost component decreases to match measured proof-submission costs, which remain below the current 3,600,000 estimate after Glamsterdam.

**Wallets and node operators.** Software that predicts fees using a local implementation of the fee formula must use the same constants as the rollup contract. A stale client-side value would produce incorrect fee predictions.

**Governance.** Governance does not gain a new parameter or activation mechanism. The constants remain compiled into the rollup implementation, keeping the existing fee model and governance surface unchanged.

## Motivation

Aztec's fee model estimates the L1 work required to propose checkpoints and verify epoch proofs. It multiplies these fixed gas estimates by the L1 gas price and incorporates the results into L2 fees. The current rollup uses:

```solidity
uint256 constant L1_GAS_PER_CHECKPOINT_PROPOSED = 300_000;
uint256 constant L1_GAS_PER_EPOCH_VERIFIED = 3_600_000;
```

Glamsterdam reprices Ethereum state creation and state access. Checkpoint proposals become materially more expensive under the new schedule. If the constants remain unchanged, the fee model will understate L1 costs after fork activation and users will underpay relative to the costs that sequencers bear.

These constants are estimates rather than exact transaction gas limits. They need to be conservative enough to support cost recovery across representative transactions, but do not need to reproduce the gas used by every transaction.

### Sepolia measurements

Glamsterdam activated on Sepolia at block 11,856,337 (2026-10-06 13:53 UTC), while the v6 testnet rollup was running there. The table below reports gas used, taken from the receipts of every v6 `propose` and `submitEpochRootProof` transaction in two windows: before the fork, from 2026-10-04 18:00 to 2026-10-06 13:36 UTC (2,092 proposals, 68 epochs), and after the fork, from 2026-10-06 13:58 to 20:36 UTC (315 proposals, 11 epochs). The linked transactions are the medians of each group.

| Transaction | Pre-fork gas (median) | Glamsterdam gas (median) | Change | Glamsterdam max |
| --- | ---: | ---: | ---: | ---: |
| `propose` | [346,496](https://sepolia.etherscan.io/tx/0x8b7e5b8dda8207c8136225841ac21e3533b2839249a23e9c28f34aeacb92e547) | [487,016](https://sepolia.etherscan.io/tx/0x7bdbd23b291b0ee1e195c9a6981bb8a1e936b1f0296c5807f0e5c04fbf0d0e68) | +40.6% | [520,242](https://sepolia.etherscan.io/tx/0x91f8a128d92cb71b3fbf9234fd0ce3262943738f0c8fdcf24e5eb35341f13d4a) |
| `propose` with `setupEpoch` (first checkpoint of an epoch) | [1,005,560](https://sepolia.etherscan.io/tx/0x994e9a708aad966d85fee05fdadc9cc6da5a5b3b330e9947d12182f38155e01c) | [1,328,058](https://sepolia.etherscan.io/tx/0x4bb88bcf5a0558294980f5b326e36e00231e3602cdb565007b8bb282bb627df1) | +32.1% | [1,340,720](https://sepolia.etherscan.io/tx/0xcf2c84b831e76028da5298f722ce6036fed618dcbeb8e46472a9c277f8d22f01) |
| `submitEpochRootProof`, first proof of an epoch | [1,968,246](https://sepolia.etherscan.io/tx/0x08a4cee2ef606d2edfe1b31a1ddce3af27cd7b484993c328edde855f285e4a01) | [2,362,132](https://sepolia.etherscan.io/tx/0x2432984b008e407b529da6dda34369d88969270b54a308467d7ef0c9d52d7eb5) | +20.0% | [2,510,996](https://sepolia.etherscan.io/tx/0x47c4e071abb5d914aac3fb7bf5cb3607ae45f7d64388aae9b7e3d82b6e23f5dc) |
| `submitEpochRootProof`, later proofs of the same epoch | [1,448,322](https://sepolia.etherscan.io/tx/0xc78cff55d2e55c49da24853d0ce676edd6bd86e06087aba3c31c042eb14f2027) | [1,546,538](https://sepolia.etherscan.io/tx/0x419c15009e70dc5407bac4e1b7965c4c7b1463a55ab0db15ea19aa63b522da9b) | +6.8% | [1,762,200](https://sepolia.etherscan.io/tx/0x390d66d3ab6e3bd8a86742c0110010f96ff581cb5b89cf98ad55c87c05abbd38) |

The first checkpoint of each epoch runs `setupEpoch`, which samples the epoch's committee and costs roughly 840,000 gas more than a regular proposal after Glamsterdam. Averaged over a 32-checkpoint epoch (31 regular proposals and one with `setupEpoch`), a checkpoint costs about 367,000 gas before the fork and about 514,000 gas after it.

The first proof of an epoch advances the proven tip and distributes rewards and fees. Later proofs of the same epoch only record the prover's submission, so they cost less. Proofs submitted through a forwarder contract rather than directly to the rollup cost about 2,885,000 gas after the fork, which includes the forwarder's own overhead.

An earlier draft of this AZIP proposed 500,000 and 4,000,000 based on local benchmarks under the Amsterdam schedule, which measured 500,356 gas for `propose` and 3,525,266 for `submitEpochRootProof`. The Sepolia proposal cost is close to that benchmark, but the epoch proof costs about 1.2 million gas less than the benchmark predicted.

## Specification

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119 and RFC 8174.

The constants MUST be:

```solidity
uint256 constant L1_GAS_PER_CHECKPOINT_PROPOSED = 520_000;
uint256 constant L1_GAS_PER_EPOCH_VERIFIED = 2_500_000;
```

All fee calculations, rounding rules, congestion calculations, fee distribution rules, and other economic parameters remain unchanged.

Any client-side implementation used to predict the mana base fee MUST use the same values. In particular, TypeScript fee prediction code, documentation of fee constants, fixtures, and tests MUST be updated together with the Solidity implementation.

The constants MUST take effect when the v6 rollup is deployed. Their activation MUST NOT depend on detection of the Ethereum fork or a subsequent governance transaction.

## Rationale

The checkpoint-proposal constant must cover the average proposal, including the `setupEpoch` cost carried by the first checkpoint of each epoch. The measured average of about 514,000 gas per checkpoint rounds up to 520,000, which also matches the most expensive regular proposal observed on Sepolia.

The epoch-verification constant must cover the proof that advances the proven tip, since that is the submission the fee model pays for once per epoch. The median first proof costs 2,362,132 gas and the most expensive full-epoch proof observed costs 2,510,996. A value of 2,500,000 covers the median with about 6% headroom. Later proofs of the same epoch and proofs routed through forwarder contracts are not covered by this estimate.

Deploying both values with v6 is the simplest way to keep the fee model adequately funded across the Ethereum fork. Glamsterdam is expected to activate on mainnet after the v6 deployment. This creates a period in which users pay a proposal component calculated for the post-fork gas schedule while proposals still cost about 367,000 gas. The temporary mismatch is limited to that component and ends without any coordinated Aztec action when Ethereum activates the new schedule.

### Alternatives considered

**Keep the existing constants.** This avoids pre-fork overpayment, but knowingly causes the fee model to understate proposal costs after Glamsterdam. Correcting the values would then require another rollup upgrade or another mechanism introduced for this purpose.

**Make the constants governance-controlled.** Governance could set new values shortly before the Ethereum activation block, optionally with delayed activation. This reduces temporary overpayment but adds storage, access control, update logic, and coordination for two approximate values that change infrequently.

**Detect the fork through fork-specific execution behavior.** A permissionless function could update the values only after a call using fork-specific behavior succeeds. This avoids governance coordination, but couples fee configuration to a brittle fork-detection mechanism and adds contract complexity solely to time this update.

The proposal chooses fixed values in v6 because the temporary overpayment is preferable to the complexity and operational risk of either activation mechanism.

## Backwards Compatibility

This proposal changes the fee produced by the v6 fee model and therefore is not numerically backwards compatible with fee predictions that retain the old constants. Transactions and fee headers use the existing formats, and no contract interface changes.

Clients that mirror the fee calculation must update in lockstep with the rollup deployment. Existing clients that obtain fee quotes from an updated node remain compatible without changes to transaction construction.

## Test Cases

- Fee calculations use 520,000 gas for each checkpoint proposal and 2,500,000 gas for each verified epoch.
- Solidity and TypeScript implementations produce identical fee components for the same L1 gas price, mana usage, proving cost, and congestion state.
- Updated fee fixtures change only the sequencer, prover, and resulting protocol fee components affected by the two constants; the congestion multiplier remains unchanged.
- At the same inputs, the checkpoint-proposal gas contribution increases by 73.3% and the epoch-verification gas contribution decreases by 30.6% relative to the old constants, subject to the existing rounding rules.
- Fee prediction and transaction submission succeed across the Ethereum fork without a governance call or a change to the rollup's configuration.

## Economics Considerations

The constants convert expected L1 gas usage into costs charged through L2 fees. Estimates below realized gas cause operators to under-recover costs, while estimates above realized gas cause users to overpay.

The checkpoint-proposal estimate rises from 300,000 to 520,000, a 73.3% increase in that component. The current 300,000 already under-recovers: Sepolia measured about 367,000 gas per checkpoint before Glamsterdam. The epoch-verification estimate falls from 3,600,000 to 2,500,000, a 30.6% decrease in that component. The current value is well above the measured cost of about 1,970,000 gas before the fork and 2,360,000 after it. These percentages do not represent the change in a user's total fee. The total effect depends on the L1 gas price, the amortization of checkpoint and epoch costs over mana, the proving-compute component, and current congestion.

Per epoch of 32 checkpoints, the two constants add up to 32 × 520,000 + 2,500,000 = 19,140,000 gas, against 13,200,000 under the current constants and about 18,800,000 measured on Sepolia after Glamsterdam.

## Security Considerations

The main risk is economic mispricing rather than a new execution or authorization vulnerability. Values that are too low can make checkpoint proposal or epoch proof submission uneconomic during high L1 gas prices. Values that are too high charge users more than the estimated L1 work requires.

The Solidity implementation and every client-side mirror must remain synchronized. A mismatch can cause nodes and wallets to predict a different fee from the value enforced by the rollup, leading to rejected proposals or transactions submitted with insufficient fees.

The constants remain immutable within a deployed rollup. If production behavior on mainnet differs materially from the Sepolia measurements, correcting them requires a new rollup implementation and the associated governance process.

This proposal introduces no new callable function, access-control path, external call, storage variable, or fork-detection dependency.

## Copyright Waiver

Copyright and related rights waived via [CC0](/LICENSE).
