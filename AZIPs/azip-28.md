# AZIP-28: Update L1 Gas Constants for Glamsterdam

## Preamble

| `azip` | `title` | `description` | `author` | `discussions-to` | `status` | `category` | `created` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 28 | Update L1 Gas Constants for Glamsterdam | Updates fee-model gas constants for checkpoint proposals and epoch proofs ahead of Ethereum's Glamsterdam fork. | Santiago Palladino (@spalladino, santiago@aztec-labs.com) | https://github.com/AztecProtocol/governance/discussions/69 | Draft | Economics | 2026-09-18 |

## Abstract

This proposal updates the fixed L1 gas estimates used by Aztec's fee model to account for Ethereum's Glamsterdam fork. The initial estimates increase the gas attributed to proposing a checkpoint from 300,000 to 500,000 and the gas attributed to verifying an epoch from 3,600,000 to 4,000,000. These proposed values are estimates derived from local benchmarks. They will be validated by running v6 under the Amsterdam gas schedule on Sepolia in early October 2026, then adjusted if necessary before the v6 mainnet deployment. Deploying the final values with v6 may cause higher pre-fork fees, but avoids underpayment and an additional governance-controlled update when the fork activates.

## Impacted Stakeholders

**Users.** The two updated estimates increase the L1-cost component of the mana base fee. Users therefore pay slightly higher L2 fees from the v6 deployment, including during the period before Glamsterdam activates. After activation, the revised fee better reflects the L1 costs borne by network operators.

**Sequencers.** The checkpoint-proposal estimate used to calculate the sequencer cost component increases. This reduces the risk that sequencers under-recover their L1 publication costs after Glamsterdam.

**Provers.** The epoch-verification estimate used to calculate the prover cost component increases. This preserves recovery of L1 proof-submission costs under the new gas schedule.

**Wallets and node operators.** Software that predicts fees using a local implementation of the fee formula must use the same constants as the rollup contract. A stale client-side value would produce incorrect fee predictions.

**Governance.** Governance does not gain a new parameter or activation mechanism. The constants remain compiled into the rollup implementation, keeping the existing fee model and governance surface unchanged.

## Motivation

Aztec's fee model estimates the L1 work required to propose checkpoints and verify epoch proofs. It multiplies these fixed gas estimates by the L1 gas price and incorporates the results into L2 fees. The current rollup uses:

```solidity
uint256 constant L1_GAS_PER_CHECKPOINT_PROPOSED = 300_000;
uint256 constant L1_GAS_PER_EPOCH_VERIFIED = 3_600_000;
```

Glamsterdam reprices Ethereum state creation and state access. Operations performed by Aztec's checkpoint-proposal and epoch-proof transactions become materially more expensive under the new schedule. If the constants remain unchanged, the fee model will understate L1 costs after fork activation and users will underpay relative to the costs that sequencers and provers must bear.

These constants are estimates rather than exact transaction gas limits. They need to be conservative enough to support cost recovery across representative transactions, but do not need to reproduce the gas used by every transaction. Benchmarks using the Amsterdam execution schedule measured the following change:

| Transaction | Pre-fork gas | Glamsterdam gas | Change |
| --- | ---: | ---: | ---: |
| `propose` | 327,076 | 500,356 | +53.0% |
| `submitEpochRootProof` | 1,521,631 | 3,525,266 | +131.7% |

These benchmarks were run in a local environment and may differ from production. The proposed values of 500,000 and 4,000,000 are estimates. Once v6 can be tested under the Amsterdam gas schedule on Sepolia in early October 2026, the constants will be measured again and adjusted as needed before the v6 mainnet deployment.

## Specification

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119 and RFC 8174.

Pending Sepolia validation, the proposed constants are:

```solidity
uint256 constant L1_GAS_PER_CHECKPOINT_PROPOSED = 500_000;
uint256 constant L1_GAS_PER_EPOCH_VERIFIED = 4_000_000;
```

These values are estimates, not final deployment measurements. All fee calculations, rounding rules, congestion calculations, fee distribution rules, and other economic parameters remain unchanged.

Any client-side implementation used to predict the mana base fee MUST use the same values. In particular, TypeScript fee prediction code, documentation of fee constants, fixtures, and tests MUST be updated together with the Solidity implementation.

The constants MUST take effect when the v6 rollup is deployed. Their activation MUST NOT depend on detection of the Ethereum fork or a subsequent governance transaction.

Before the v6 mainnet deployment, the estimates MUST be validated by measuring v6 on Sepolia under the Amsterdam gas schedule. The final measured values MUST be recorded in this AZIP, and the Solidity and client implementations MUST use those values. If the measurements materially differ from the local benchmarks, this AZIP and the implementation MUST be updated before deployment.

## Rationale

The selected values are conservative round estimates based on local benchmarks. They are provisional until v6 can be measured under the Amsterdam gas schedule on Sepolia in early October 2026. Those measurements will determine whether either value needs adjustment before the v6 mainnet deployment.

Deploying both values with v6 is the simplest way to keep the fee model adequately funded across the Ethereum fork. Glamsterdam is expected to activate after the v6 deployment. This creates a period in which users pay fees calculated with the higher constants under the pre-fork gas schedule. The temporary mismatch is limited to the affected L1-cost components and ends without any coordinated Aztec action when Ethereum activates the new schedule; ordinary estimation headroom remains.

### Alternatives considered

**Keep the existing constants.** This avoids pre-fork overpayment, but knowingly causes the fee model to understate operator costs after Glamsterdam. Correcting the values would then require another rollup upgrade or another mechanism introduced for this purpose.

**Make the constants governance-controlled.** Governance could set new values shortly before the Ethereum activation block, optionally with delayed activation. This reduces temporary overpayment but adds storage, access control, update logic, and coordination for two approximate values that change infrequently.

**Detect the fork through fork-specific execution behavior.** A permissionless function could update the values only after a call using fork-specific behavior succeeds. This avoids governance coordination, but couples fee configuration to a brittle fork-detection mechanism and adds contract complexity solely to time this update.

The proposal chooses fixed values in v6 because the temporary overpayment is preferable to the complexity and operational risk of either activation mechanism.

## Backwards Compatibility

This proposal changes the fee produced by the v6 fee model and therefore is not numerically backwards compatible with fee predictions that retain the old constants. Transactions and fee headers use the existing formats, and no contract interface changes.

Clients that mirror the fee calculation must update in lockstep with the rollup deployment. Existing clients that obtain fee quotes from an updated node remain compatible without changes to transaction construction.

## Test Cases

- Fee calculations use the final constants recorded after Sepolia validation; until then, tests use the proposed estimates of 500,000 gas for each checkpoint proposal and 4,000,000 gas for each verified epoch.
- Solidity and TypeScript implementations produce identical fee components for the same L1 gas price, mana usage, proving cost, and congestion state.
- Updated fee fixtures change only the sequencer, prover, and resulting protocol fee components affected by the two constants; the congestion multiplier remains unchanged.
- At the same inputs, the checkpoint-proposal gas contribution increases by 66.7% and the epoch-verification gas contribution increases by 11.1% relative to the old constants, subject to the existing rounding rules.
- Fee prediction and transaction submission succeed across the Ethereum fork without a governance call or a change to the rollup's configuration.

## Economics Considerations

The constants convert expected L1 gas usage into costs charged through L2 fees. Increasing them transfers the risk of estimation error away from sequencers and provers and toward users: estimates below realized gas cause operators to under-recover costs, while estimates above realized gas cause users to overpay.

The checkpoint-proposal estimate rises from 300,000 to 500,000, a 66.7% increase in that component. The epoch-verification estimate rises from 3,600,000 to 4,000,000, an 11.1% increase in that component. These percentages do not represent the increase in a user's total fee. The total effect depends on the L1 gas price, the amortization of checkpoint and epoch costs over mana, the proving-compute component, and current congestion.

Before Glamsterdam, both updated components are conservative. Available production references indicate approximately 350,000 gas for a proposal and 1.75 million gas for an epoch-proof submission under the current schedule. The epoch constant is already deliberately above observed execution cost, so its small increase can accommodate a much larger percentage change in the measured transaction cost. After Glamsterdam, benchmark results of approximately 500,000 and 3.5 million gas place both new constants near or above the measured costs.

The proposed values remain estimates until v6 is measured under the Amsterdam gas schedule on Sepolia in early October 2026. This AZIP and the implementation MUST be revised together if those measurements show a material difference, so the v6 mainnet deployment uses values grounded in the testnet results.

## Security Considerations

The main risk is economic mispricing rather than a new execution or authorization vulnerability. Values that are too low can make checkpoint proposal or epoch proof submission uneconomic during high L1 gas prices. Values that are too high charge users more than the estimated L1 work requires.

The Solidity implementation and every client-side mirror must remain synchronized. A mismatch can cause nodes and wallets to predict a different fee from the value enforced by the rollup, leading to rejected proposals or transactions submitted with insufficient fees.

The constants remain immutable within a deployed rollup. If the final Glamsterdam gas schedule or production behavior differs materially from the estimates, correcting them requires a new rollup implementation and the associated governance process. Testnet measurements should therefore be reviewed before the mainnet payload is finalized.

This proposal introduces no new callable function, access-control path, external call, storage variable, or fork-detection dependency.

## Copyright Waiver

Copyright and related rights waived via [CC0](/LICENSE).
