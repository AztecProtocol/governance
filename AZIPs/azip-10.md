# AZIP-10: Rename Tagging Key

## Preamble

| `azip` | `title` | `description` | `author` | `discussions-to` | `status` | `category` | `created` |
|-----|-|-|-|-|-|-|-|
| 10 | Rename Tagging Key | Rename the unused tagging-key slot in the contract instance to signing key | Ilyas Ridhuan (@IlyasRidhuan) | - | Draft | Core | 2026-04-29 |


## Abstract
Aztec's `PublicKeys` struct currently includes a tagging public key (`tpk`) and a corresponding tagging secret key (`tsk`). However, tagging for note discovery is in fact currently derived from the sender's `ivsk` and the `tsk` is unused.

This AZIP proposes renaming `tpk` / `tsk` to `spk` / `ssk` (signing public key / signing secret key) to semantically align it with its future use as a means for contracts to sign messages.

## Impacted Stakeholders

This AZIP changes a struct field name and the secret-key derivation domain separator, so every stakeholder that consumes, displays, or persists the `PublicKeys` struct or its derived keys is affected.

### App Developers
Noir contract authors who consume `get_public_keys(account)` see the field rename `tpk` → `spk`. Existing contracts that reference `tpk_m`, `TpkM`, `tagging_key`, or related identifiers will not compile and must be updated.

### Infrastructure Providers (Indexers, P2P Nodes, Block Explorers)
Decoders that reference fields by name MUST be updated.

### Wallets
The `PublicKeys` struct field name changes from `tpk` / `tpk_hash` to `spk` / `spk_hash`.
Wallets need to update their derivation of secrets and addresses.

While wallets that persist the secret keys directly (i.e. store `tsk` rather than re-deriving it from a seed) can carry their existing keys forward and preserve the account address, this is not recommended as it is fragile to legacy code paths.


## Motivation

A dedicated key committed to an Aztec address that can be used by contracts to sign messages on behalf of the contract owner is a useful construct. This key is not a replacement for the tx authorisation mechanism (e.g. AuthWits) and should only be used to sign
non-state modifying transactions.

## Specification

> The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119 and RFC 8174.

### Overview of Renames

| Before | After |
|--------|-------|
| `tpk` / `Tpk` | `spk` / `Spk` |
| `TpkM` (struct) | `SpkM` (struct) |
| `tpk_m`, `tpk_m_hash` | `spk_m`, `spk_m_hash` |
| `tsk`, `tsk_m` | `ssk`, `ssk_m` |
| `DOM_SEP__TSK_M` | `DOM_SEP__SSK_M` |
| `DEFAULT_TPK_M_X` / `_Y` | `DEFAULT_SPK_M_X` / `_Y` |
| `masterTaggingPublicKey` | `masterSigningPublicKey` |
| `masterTaggingSecretKey` | `masterSigningSecretKey` |

### Change to the `PublicKeys` Struct
The protocol-circuits `PublicKeys` struct SHALL be:

```noir
pub struct PublicKeys {
    pub nhpk: NhpkM,
    pub ivpk: IvpkM,
    pub ovpk: OvpkM,
    pub spk:  SpkM, // was: TpkM
}
```

### Change to the Secret-Key Derivation Domain Separator
The domain separator MUST be renamed `DOM_SEP__TSK_M` → `DOM_SEP__SSK_M`.

```noir
DOM_SEP__SSK_M = poseidon2_hash_bytes(b"az_dom_sep__ssk_m")
```
### Change to the Contract Instance and Event Payload
The `ContractInstance` and `ContractInstancePublished` struct field referencing `TpkM` MUST be renamed.

### Change to the Oracle Interface
The oracle that returns public keys to a private function MUST return the renamed `spk` field in place of `tpk`. Identifier strings used as oracle keys MUST be updated.

### Change to Kernel Circuits
Kernel circuits that validate the contract address of the function call being processed MUST reference `SpkM` when re-deriving and checking `public_keys_hash`. The hashing inputs and output are unchanged.

## Rationale

Since the tagging key is unused by the protocol, by re-using it for this purpose we minimise the invasiveness of the change.

### Address Changes
While the address derivation is unchanged, whether a given account's address changes under this AZIP depends on whether the value stored at the renamed slot changes:
- A wallet that persists `tsk_m` can carry the same `Field` value forward as `spk_m`. The derived `public_keys_hash` is identical and the address is preserved.
- A wallet that re-derives the secret key from a seed sees its derived value change because of the domain-separator change.

It is RECOMMENDED that wallets re-derive the secret key and new address to not be reliant on legacy code paths.

### Why change the secret-key domain separator preimage
A new domain separator is used to preserve consistency across the protocol. This comes at the cost of invalidating keys and addresses derived prior to this AZIP.

An alternative of maintaining the original domain separator was explored but ultimately it was decided that permanently embedding the legacy notion of a `tsk` into the protocol was undesirable.

### Change to aztec-nr APIs
The following public API surface in aztec-nr MUST be updated:
- field name `tpk_m`, `TpkM`, `tagging_key` in any struct or accessor exposed to contract authors,
- comments and doc-strings referencing "tagging" tied to this key MUST be updated to "signing".

### Documentation Updates
All references to "tagging key" / "tagging public key" / "tagging secret key" tied to the renamed slot MUST be updated to the signing-key terminology. References to "tagging" in the context of note discovery (sender-`ivsk`-derived tags) are out of scope and MUST be preserved.

## Backwards Compatibility

This proposal is NOT backward compatible and represents a breaking change to the protocol. This AZIP MUST therefore be shipped as part of a new Aztec rollup version.

1. **Source-level breakage.** Any contract, indexer, or tool referencing `tpk`, `tsk`, `TpkM`, `DOM_SEP__TSK_M`, `KeyPrefix='t'`, or related identifiers will not compile or will fail schema validation.
2. **Key Derivation is invalidated** Any wallets that re-derive from a given master secret will no longer be able to generate the previous `tsk`. Additionally, re-derived addresses will be different.
3. **Event payload bytes unchanged.** Indexers that decode the `ContractInstancePublished` event by field offset remain compatible. Indexers that decode by field name MUST be updated.

## Copyright Waiver:
Copyright and related rights waived via [CC0](https://github.com/AztecProtocol/governance/blob/main/LICENSE).
