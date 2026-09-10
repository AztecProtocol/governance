# AZIP-21: Rename Fee Juice to AZTEC

## Preamble

| `azip` | `title` | `description` | `author` | `discussions-to` | `status` | `category` | `created` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 21 | Rename Fee Juice to AZTEC | Renames the Fee Juice fee-payment asset and every associated identifier to AZTEC, using `aztec_fee_payment_token` for internal names, to reflect that it is bridged $AZTEC used to pay fees. | David (@rolldavid, david@aztec.foundation) | - | Draft | Core | 2026-06-22 |

## Abstract

The protocol's enshrined fee-payment asset is currently named **Fee Juice**. This name does not convey what the asset actually is: the in-protocol representation of the **$AZTEC** ERC20 token, bridged from L1, that is spent to pay transaction fees. This AZIP renames the asset and all identifiers derived from it.

Two naming registers are defined. Public-facing identifiers — the Noir contract, SDK classes, getters, and the protocol-contract enum member — use **`AZTEC`** (e.g. `AZTEC::at(address)`, `AZTECPaymentMethod`, `AZTECPaymentMethodWithClaim`, `getAZTEC`, `ProtocolContractAddress.AZTEC`). Internal identifiers — module/file/directory names, storage, protocol constants, and local variables — use **`aztec_fee_payment_token`** (e.g. `aztec_fee_payment_token_contract`, `AZTEC_FEE_PAYMENT_TOKEN_ADDRESS`). The change is purely lexical: the canonical address (`5`), the balances storage slot (`1`), the storage layout, the L1↔L2 bridge mechanics, and all wire/serialization formats are unchanged.

## Impacted Stakeholders

**App Developers.** This is a breaking change to the public SDK surface. The most widely used symbols — `FeeJuicePaymentMethod`, `FeeJuicePaymentMethodWithClaim`, `FeeJuiceContract`, `getFeeJuiceBalance`, and `ProtocolContractAddress.FeeJuice` — are renamed. Any application, account contract, or script that imports these MUST update its imports. Because the underlying address, storage layout, and fee-payment behavior are unchanged, no redeployment or state migration is required; the change is source-level only. A deprecation shim MAY be shipped for one release to ease migration (see Backwards Compatibility).

**Wallets.** Wallets that bridge the fee asset, construct fee-payment methods, or display a fee-asset balance MUST update to the renamed SDK symbols and to the renamed CLI command (`bridge-fee-juice` → `bridge-aztec`). User-facing strings ("Fee Juice") MUST be updated to "AZTEC".

**Infrastructure Providers (Indexers, RPCs, Block Explorers).** Node configuration and environment variables change (`FEE_JUICE_CONTRACT_ADDRESS` → `AZTEC_FEE_PAYMENT_TOKEN_CONTRACT_ADDRESS`, `FEE_JUICE_PORTAL_CONTRACT_ADDRESS` → `AZTEC_PORTAL_CONTRACT_ADDRESS`). Tools that surface a human-readable contract name for the address-`5` contract will report `AZTEC` instead of `FeeJuice`. No on-chain data format changes.

**Sequencers and Provers.** No behavioral change. The base-rollup circuits continue to read the fee payer's balance from the same contract address and storage slot; only the constant *names* (`FEE_JUICE_ADDRESS`, `FEE_JUICE_BALANCES_SLOT`) and the fee-payer balance read-hint field name change. Regenerated circuit artifacts and constants files MUST be re-derived, but the proving system, public inputs, and verification keys for fee handling are functionally unchanged.

## Motivation

"Fee Juice" is an opaque name. It tells a newcomer nothing about the asset's purpose, its denomination, or its relationship to the network's native token. In practice the asset *is* the $AZTEC token: a holder bridges $AZTEC from L1 through the fee portal, receives a balance in the enshrined L2 contract, and spends that balance to pay transaction fees. The current name obscures three facts that matter to every developer and user touching fees:

1. **The fee asset is $AZTEC.** Fees are denominated in and paid with the network's native token, not a separate "juice" resource.
2. **The asset is bridged from L1.** Acquiring a spendable fee balance requires bridging an L1 ERC20 into the network via the fee portal and claiming it on L2.
3. **Its sole utility is paying fees.** The enshrined contract is not a general-purpose token; it is the fee-payment representation of bridged $AZTEC.

The existing protocol specification names this asset `FeeJuice` throughout — in the canonical Noir contract, in protocol constants, in the L1 portal contract, and across the entire SDK surface that application developers rely on. No amount of documentation fully overcomes a confusing primary identifier that appears in every fee-related import, class name, and config key a developer encounters. Renaming the identifiers to reflect what the asset is — bridged $AZTEC used to pay fees — removes that confusion at the source.

## Specification

> The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119 and RFC 8174.

### Naming registers

Two registers SHALL be used consistently:

- **Public register — `AZTEC`.** Used for public-facing type and symbol names: the enshrined Noir contract, its `::at(address)` handle, SDK classes, exported getters/factories, the L1 portal contract, and the `ProtocolContractAddress` enum member. PascalCase types take the form `AZTEC*` (e.g. `AZTECPaymentMethod`); getters take the form `get…AZTEC…`.
- **Internal register — `aztec_fee_payment_token`.** Used for all internal identifiers: Noir module/file/directory names, storage variables, protocol constants (in `SCREAMING_SNAKE_CASE` as `AZTEC_FEE_PAYMENT_TOKEN_*`), and the camelCase form `aztecFeePaymentToken` for local variables and struct fields.

The choice of register for any single identifier SHALL be determined by what the identifier names: a public API symbol uses the public register; an internal name, file, directory, storage slot, or local binding uses the internal register. Casing SHALL follow the conventions of the surrounding language (PascalCase for Noir contracts and TS classes; `snake_case` for Noir items and files; `SCREAMING_SNAKE_CASE` for constants and environment variables; camelCase for TS/JS locals and fields).

This AZIP governs **all** identifiers derived from "Fee Juice" (any case: `FeeJuice`, `fee_juice`, `feeJuice`, `FEE_JUICE`, "Fee Juice"), not only those enumerated below. At the time of writing this is approximately **1,527 occurrences across roughly 249 files**.

### Invariants — MUST NOT change

The rename is strictly lexical. The following SHALL remain unchanged:

- The canonical contract address. `AZTEC_FEE_PAYMENT_TOKEN_ADDRESS` SHALL equal `5`, exactly as `FEE_JUICE_ADDRESS` does today.
- The balances storage slot. `AZTEC_FEE_PAYMENT_TOKEN_BALANCES_SLOT` SHALL equal `1`, exactly as `FEE_JUICE_BALANCES_SLOT` does today.
- The storage layout of the enshrined contract (the `balances: Map<AztecAddress, PublicMutable<u128>>` read directly by the base-rollup circuits).
- The function signatures and selectors of the enshrined contract (`claim`, `_increase_public_balance`, `check_balance`, `balance_of_public`) — none of these names contain "Fee Juice" and therefore none change.
- The L1↔L2 bridge message format and the `claim(bytes32,uint256)` content-hash preimage used by the portal.
- All public-input shapes, wire formats, and serialization of fee-related protocol-circuit data.

### Enshrined Noir contract

The protocol contract at `noir-projects/noir-contracts/contracts/protocol/fee_juice_contract` SHALL be renamed:

- The contract declaration `pub contract FeeJuice` SHALL become `pub contract AZTEC`, so that call sites read `AZTEC::at(context.this_address())`.
- The package directory `fee_juice_contract` SHALL become `aztec_fee_payment_token_contract`, and the package name updated accordingly.

### Protocol constants

In `noir-projects/noir-protocol-circuits/crates/types/src/constants.nr` and every generated mirror (`yarn-project/constants/src/constants.gen.ts`, `l1-contracts/src/core/libraries/ConstantsGen.sol`, `barretenberg/cpp/src/barretenberg/vm2/common/aztec_constants.hpp`, and the `constants.in.ts` source):

| Old constant (value) | New constant (value unchanged) |
| --- | --- |
| `FEE_JUICE_ADDRESS` = `5` | `AZTEC_FEE_PAYMENT_TOKEN_ADDRESS` = `5` |
| `FEE_JUICE_BALANCES_SLOT` = `1` | `AZTEC_FEE_PAYMENT_TOKEN_BALANCES_SLOT` = `1` |

### L1 contracts

| Old (Solidity) | New |
| --- | --- |
| `FeeJuicePortal` (`l1-contracts/src/core/messagebridge/FeeJuicePortal.sol`) | `AZTECPortal` |
| `IFeeJuicePortal` (`.../interfaces/IFeeJuicePortal.sol`) | `IAZTECPortal` |
| `MockFeeJuicePortal` (`.../mock/MockFeeJuicePortal.sol`) | `MockAZTECPortal` |

The portal's `UNDERLYING` ERC20 is the $AZTEC token; the rename makes that relationship explicit. The portal's external function names (`depositToAztecPublic`, etc.) do not contain "Fee Juice" and SHALL NOT change.

### SDK (aztec.js / protocol-contracts / stdlib / ethereum)

Representative public-register mappings (non-exhaustive):

| Old identifier | New identifier |
| --- | --- |
| `FeeJuicePaymentMethod` | `AZTECPaymentMethod` |
| `FeeJuicePaymentMethodWithClaim` | `AZTECPaymentMethodWithClaim` |
| `FeeJuiceContract` | `AZTECContract` |
| `getFeeJuiceBalance` | `getAZTECBalance` |
| `getCanonicalFeeJuice` | `getCanonicalAZTEC` |
| `getFeeJuiceArtifact` / `FeeJuiceArtifact` / `FeeJuiceJson` | `getAZTECArtifact` / `AZTECArtifact` / `AZTECJson` |
| `FeeJuiceAbi` / `FeeJuicePortalAbi` | `AZTECAbi` / `AZTECPortalAbi` |
| `ProtocolContractAddress.FeeJuice` | `ProtocolContractAddress.AZTEC` |

Internal-register mappings (non-exhaustive):

| Old identifier | New identifier |
| --- | --- |
| `feeJuice` (variable) | `aztecFeePaymentToken` |
| `feeJuiceContract` (variable) | `aztecFeePaymentTokenContract` |
| `feePayerFeeJuiceBalanceReadHint` / `fee_payer_fee_juice_balance_read_hint` | `feePayerAztecFeePaymentTokenBalanceReadHint` / `fee_payer_aztec_fee_payment_token_balance_read_hint` |
| directory `protocol-contracts/src/fee-juice/` | `protocol-contracts/src/aztec-fee-payment-token/` |
| file `fee_juice_payment_method.ts` | `aztec_payment_method.ts` |
| file `fee_juice_payment_method_with_claim.ts` | `aztec_payment_method_with_claim.ts` |

Filenames SHALL track the register of their primary exported symbol: a file whose primary export is a public-register class takes the `aztec_*` form matching that class; a file with no single public symbol takes the internal `aztec_fee_payment_token_*` form.

### Configuration, environment variables, and CLI

| Old | New |
| --- | --- |
| env `FEE_JUICE_CONTRACT_ADDRESS` | `AZTEC_FEE_PAYMENT_TOKEN_CONTRACT_ADDRESS` |
| env `FEE_JUICE_PORTAL_CONTRACT_ADDRESS` | `AZTEC_PORTAL_CONTRACT_ADDRESS` |
| CLI command `bridge-fee-juice` | `bridge-aztec` |
| config `feeJuicePortalInitialBalance` | `aztecPortalInitialBalance` |

### User-facing strings and documentation

All display strings and documentation referring to "Fee Juice" SHALL be updated to "AZTEC". Where additional context aids the reader, prose MAY describe it as "AZTEC, the bridged fee-payment token".

## Rationale

### Why two registers instead of one

A single token would be either too terse or too verbose everywhere. `AZTEC` alone, used for an internal storage slot or a module path, is ambiguous with the network, the L1 ERC20, and the organization. `aztec_fee_payment_token` everywhere — including in the names application developers type dozens of times (`AZTECPaymentMethod`) — is needlessly long. Splitting by audience resolves this: the public API stays short and recognizable (`AZTEC`), while internal names stay precise and self-documenting (`aztec_fee_payment_token`). This mirrors the requested convention (`AZTECPaymentMethod`, `AZTEC::at(...)`) directly.

### Why `AZTEC` for the contract handle

Naming the enshrined contract `AZTEC` makes call sites read as `AZTEC::at(address)`, which states plainly that the fee asset *is* AZTEC. This is the single most-read identifier for anyone tracing fee payment and is where the clarity benefit is largest.

### Alternatives considered

- **Keep `FeeJuice` and rely on documentation.** Rejected: the confusing identifier appears in every fee-related import and config key; documentation cannot fully compensate for a primary symbol that misleads.
- **Rename to a different name (e.g. `FeeToken`, `GasToken`).** Rejected: these still hide that the asset is the native $AZTEC token bridged from L1, which is the specific fact the rename exists to surface.
- **Use `AZTEC` for internal names too.** Rejected for ambiguity with the network/token/org, as above.
- **Change the canonical address or storage slot as part of the cleanup.** Rejected: that would convert a cosmetic rename into a breaking protocol change requiring a new rollup version and state migration, for no benefit. The numeric invariants are deliberately preserved.

## Backwards Compatibility

This AZIP is a **breaking change at the source level** (SDK imports, env vars, CLI command, and the human-readable contract name) but is **fully backwards compatible at the protocol/state level**.

- **Protocol/state.** The canonical address (`5`), balances slot (`1`), storage layout, contract function selectors, and L1↔L2 bridge format are unchanged. Existing balances, in-flight bridge claims, and deployed apps that pay fees continue to work without redeployment or migration. The base-rollup circuits read the same address and slot; only constant *names* change.
- **Contract class identifier.** Renaming the Noir contract and its package regenerates the contract artifact. If the canonical contract class identifier is derived from artifact metadata that includes the contract name, the regenerated artifact will yield a new class identifier, and the canonical class-id constant in `protocol-contracts` MUST be regenerated to match. This does not affect fee-payment correctness, because protocol circuits key off the fixed address (`5`) and slot (`1`), not the class identifier or the contract name.
- **SDK consumers.** Imports of the renamed symbols MUST be updated. To smooth migration, the implementation MAY export deprecated aliases (e.g. `export { AZTECPaymentMethod as FeeJuicePaymentMethod }`) for **one** release, emitting a deprecation warning, and remove them in the following release. Whether to ship aliases is an implementation decision and does not alter the specification.

Because there is no on-chain or state incompatibility, this AZIP does **not** require a new rollup version. It SHOULD be bundled into a release as a coordinated source change so that the codebase, generated artifacts, constants files, and documentation are renamed atomically.

This AZIP carries **no on-chain payload** and therefore requires **no AZUP execution**: it produces no on-chain actions for a payload's `getActions()` to encode, and consequently no sequencer signaling, tokenholder vote, or governance execution is needed. Acceptance is a coordination decision; the change is delivered entirely as source PRs against the implementation and shipped in a normal software release, taking effect (cosmetically) in the contracts of any future rollup deployment. Editors MAY elect to track it as a list-only AZUP with an empty payload, but no [AZUP](../azup-process.md) onchain step is required.

## Test Cases

- Every existing fee-payment test (e.g. the `e2e_fees` suite, `avm_public_fee_payment`, gas-validator tests) MUST pass unchanged in behavior after the rename, referencing the renamed symbols.
- A build-time assertion SHALL confirm `AZTEC_FEE_PAYMENT_TOKEN_ADDRESS == 5` and `AZTEC_FEE_PAYMENT_TOKEN_BALANCES_SLOT == 1` across all generated constants mirrors (Noir, TS, Solidity, C++), guaranteeing the numeric invariants survived the rename.
- A repository-wide check SHALL confirm that no identifier matching `/fee.?juice/i` remains, except where retained intentionally as a documented deprecation alias.
- A test SHALL confirm that bridging via the renamed `AZTECPortal` and claiming via the enshrined contract credits the same balance as before the rename.

## Reference Implementation

Primary sites to rename:

- Enshrined contract: `noir-projects/noir-contracts/contracts/protocol/fee_juice_contract/` (`src/main.nr`, `src/lib.nr`).
- Protocol constants: `noir-projects/noir-protocol-circuits/crates/types/src/constants.nr` and generated mirrors (`yarn-project/constants/src/constants.gen.ts`, `.../constants.in.ts`, `l1-contracts/src/core/libraries/ConstantsGen.sol`, `barretenberg/cpp/.../aztec_constants.hpp`).
- L1 portal: `l1-contracts/src/core/messagebridge/FeeJuicePortal.sol`, `.../interfaces/IFeeJuicePortal.sol`, `.../mock/MockFeeJuicePortal.sol`.
- SDK payment methods: `yarn-project/aztec.js/src/fee/fee_juice_payment_method.ts`, `.../fee_juice_payment_method_with_claim.ts`, plus `aztec.js/src/api/fee.ts`, `aztec.js/src/contract/protocol_contracts.ts`, `aztec.js/src/utils/fee_juice.ts`.
- Protocol-contract registry: `yarn-project/protocol-contracts/src/fee-juice/`, `.../protocol_contract_data_2.ts`, `.../provider/`, `.../scripts/generate_data.ts`; and `yarn-project/stdlib/src/contract/interfaces/protocol_contract_addresses.ts`.
- Config/env: `yarn-project/foundation/src/config/env_var.ts`, `yarn-project/ethereum/src/l1_contract_addresses.ts`, `yarn-project/ethereum/src/deploy_l1_contracts.ts`, and deployment manifests (`docker-compose.yml`, terraform).
- CLI: `yarn-project/cli-wallet/src/cmds/bridge_fee_juice.ts` and its registration.

## Security Considerations

- **Purely lexical change.** The rename introduces no new code paths, no change to fee accounting, and no change to the bridge trust model. The principal risk is an *incomplete or inconsistent* rename, not a behavioral one.
- **Constant-value drift.** The dominant risk is accidentally changing the numeric value of the canonical address or balances slot while renaming the constant. The Test Cases REQUIRE a build-time assertion pinning both values, so any drift fails the build rather than silently corrupting fee reads in the base-rollup circuits.
- **Generated-artifact consistency.** Constants are mirrored across Noir, TypeScript, Solidity, and C++ from a single source. The rename MUST regenerate all mirrors from that source in one change; a partial rename that leaves one mirror with the old name (but correct value) is a build hazard and MUST be caught by the no-`/fee.?juice/i`-remaining check.
- **Deprecation aliases.** If temporary aliases are shipped, they MUST resolve to the identical underlying symbol/address so that an app using the old name and an app using the new name interact with the same contract at address `5`. Aliases MUST be removed on the stated schedule to avoid a permanent dual-naming surface.
- **No privacy or economic impact.** Fees are paid from the same balances at the same address; the rename neither adds nor removes any information disclosure, and changes no economic parameter.

## Copyright Waiver

Copyright and related rights waived via [CC0](/LICENSE).
