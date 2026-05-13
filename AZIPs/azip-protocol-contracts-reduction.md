# Reduce Protocol Contract Set

## Preamble

| `azip` | `title`                      | `description`                                                                                                                 | `author`                | `discussions-to` | `status` | `category` | `created`  |
| ------ | ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------- | ----------------------- | ---------------- | -------- | ---------- | ---------- |
|        | Reduce Protocol Contract Set | Remove AuthRegistry, MultiCallEntrypoint, and PublicChecks from the protocol contracts and down-shift the remaining addresses | David Banks (@dbanks12) | N/A              | Draft    | Core       | 2026-05-13 |

## Abstract

This AZIP removes `AuthRegistry`, `MultiCallEntrypoint`, and `PublicChecks` from the protocol contract set and reassigns the remaining three contracts — `ContractInstanceRegistry`, `ContractClassRegistry`, and `FeeJuice` — to addresses `1`, `2`, and `3`. The demoted contracts may continue to be deployed as ordinary user-space contracts without privileged status.

## Impacted Stakeholders

App developers, wallets, tooling (`aztec.js`, PXE), sequencers, provers, and infrastructure providers (block explorers, indexers, RPCs) will need to update any hardcoded references to the three demoted contracts to point at user-space deployments, and to rebuild against the new addresses for the three retained protocol contracts.

## Motivation

The protocol contract set is enshrined in the genesis state at fixed addresses, a commitment every client, circuit, and contract depends on. The set should contain only contracts the protocol itself consults at known addresses: the contract instance and class registries (used during instance/class resolution) and the fee juice contract (used during fee collection).

`AuthRegistry`, `MultiCallEntrypoint`, and `PublicChecks` were enshrined during early bring-up of the protocol and `aztec-nr`. None requires enshrinement to function:

- `AuthRegistry` is a public authwit ledger; any deployment can serve that role provided callers know where to find it.
- `MultiCallEntrypoint` is an entrypoint contract selected by accounts and tools, not the protocol.
- `PublicChecks` is a library of public assertions with no state and no privileged operations.

Compacting the remaining contracts to addresses `1`, `2`, `3` avoids permanently reserving holes in the low-integer address space.

## Specification

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119 and RFC 8174.

### Removed protocol contracts

`AuthRegistry`, `MultiCallEntrypoint`, and `PublicChecks` MUST no longer be members of the protocol contract set. The genesis state MUST NOT include instances of these contracts, no protocol contract address MUST resolve to any of them, and the protocol MUST NOT grant them privileged treatment, address aliasing, or implicit deployment. They MAY continue to exist as ordinary contracts deployed via the standard contract instance flow.

### Protocol contract address assignments

The protocol contract address space MUST be exactly:

| Address | Contract                   |
| ------- | -------------------------- |
| `1`     | `ContractInstanceRegistry` |
| `2`     | `ContractClassRegistry`    |
| `3`     | `FeeJuice`                 |

All other low-integer addresses MUST be treated as unassigned and MUST NOT resolve to any protocol contract. The genesis protocol contracts tree MUST be rebuilt over this three-entry set, and its root — referenced by the protocol circuits and the rollup contract — MUST be updated accordingly.

### Constants

The protocol contract address constants for `ContractInstanceRegistry` (`2` → `1`), `ContractClassRegistry` (`3` → `2`), and `FeeJuice` (`5` → `3`) MUST be updated. These addresses are referenced throughout the stack — protocol circuits, the AVM, the sequencer, the PXE, `aztec.js` — via Noir/TypeScript/C++ constants generated from a single source, so this is not a manual per-callsite migration. Every constant, manifest entry, deployer registration, and address-resolution path keyed on the three demoted contracts as protocol contracts MUST be removed.

## Rationale

**Bundling.** The three removals are proposed together because each individual removal would leave a hole in the address space; bundling lets the compaction happen once.

**Compaction.** Preserving the historical sparse mapping (`2`, `3`, `5`) would permanently reserve `1`, `4`, `6`. Compaction is preferred because no application logic depends on specific numeric values — addresses are referenced through named constants.

## Backwards Compatibility

This is a breaking change. Every protocol contract address changes, and three contracts cease to be protocol contracts. Contracts and tooling that hard-code literal protocol contract addresses MUST be updated; imports of the demoted contracts MUST be repointed to a user-space deployment; wallets relying on `AuthRegistry` for public authwits MUST select a specific deployment. Activation coincides with a network upgrade. There is no in-band migration path; clients and contracts compiled against the old constants will not interoperate with a chain that has activated this AZIP.

## Test Cases

1. **Genesis tree.** The protocol contracts tree contains exactly three entries (`ContractInstanceRegistry` at `1`, `ContractClassRegistry` at `2`, `FeeJuice` at `3`) and its root matches the value embedded in the rollup contract.
2. **Removed contracts are not protocol contracts.** Resolving addresses `4`, `5`, or `6` MUST NOT return a protocol contract.
3. **End-to-end tests.** The existing end-to-end suite — private/public transfers, contract deployment, fee payment, and authwit flows that explicitly deploy `AuthRegistry` — passes against the updated constants.
4. **Constant consistency.** The Noir, TypeScript, and C++ exports of each protocol contract address resolve to the same value.

## Security Considerations

**Loss of enshrined status for `AuthRegistry`.** Public authwit checks have historically resolved through `AuthRegistry` at a known protocol address. After this AZIP activates, callers must select a specific deployment they trust.

**Loss of enshrined status for `MultiCallEntrypoint`.** Accounts that use `MultiCallEntrypoint` already encode their entrypoint address. Removing the enshrined deployment does not weaken any account's authentication model, but accounts choosing differently-deployed instances will route through different code and storage. Account libraries SHOULD pin a specific deployment.

**Genesis tree commitment.** The root of the new protocol contracts tree becomes part of the genesis commitment. Its construction MUST be reviewed before activation; an incorrect root would silently change which contract a protocol address resolves to.

**No change to contract behavior.** This AZIP does not modify any of the six contracts involved. Existing security properties are preserved; the demoted contracts retain them in user space, and the retained contracts retain them at new addresses.

## Copyright Waiver

Copyright and related rights waived via [CC0](/LICENSE).
