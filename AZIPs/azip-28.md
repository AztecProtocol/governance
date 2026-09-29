# AZIP-29: Protocol Nullifier Refinement

## Preamble

| `azip` | `title` | `description` | `author` | `discussions-to` | `status` | `category` | `created` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 29 | Protocol Nullifier Refinement | Derives the protocol nullifier from the tx request's origin, chain id, version and salt only, so a fee bump or cancellation shares it. | Mike Connor (@iAmMichaelConnor) | N/A | Approved | Core | 2026-09-21 |


## Abstract

Every Aztec transaction carries a protocol nullifier: a nullifier the init kernel inserts at index 0 of the transaction's nullifiers, regardless of what the transaction does. It exists so that the kernels can derive a unique nonce for every note the transaction creates, which is the protocol's defence against Faerie-Gold attacks. Its value has been the hash of the entire tx request, including gas settings and the arguments of the first call.

This AZIP redefines the protocol nullifier's preimage to four fields: the tx request's `origin`, `chain_id`, `version` and `salt`. Gas settings, the function selector and the argument hash of the first call leave the preimage. The proof remains bound to the full tx request by the init kernel's existing checks. The consequence is that two transactions built by the same origin from the same salt are mutually exclusive: at most one can be mined. A wallet that wants to bump a transaction's fee, or cancel it, reuses the salt and needs no additional nullifier. A wallet that wants independent transactions draws a fresh salt for each, as wallets do today.

Nothing that exists today stops working. Every current Aztec.js, Aztec.nr, PXE and aztec-kit paradigm for building, authorising and paying for transactions remains valid and behaves as before, because none of them depends on how the protocol nullifier is derived. The properties this AZIP enables are additive: accounts, wallets and libraries can adopt them when they choose, one at a time, without a coordinated migration.

## Impacted Stakeholders

**Wallets.** The `salt` field of the tx request can be interpreted as the transaction's nonce. Wallets already draw it uniformly at random per transaction, and nothing changes for a wallet that keeps doing so. A wallet MAY deliberately reuse the salt of a pending transaction to build a replacement (higher fee, or a no-op cancellation) that excludes the original. No change is required to ship this AZIP.

**App developers and account contract authors.** Nothing changes in this AZIP for contracts. Every existing Aztec.nr pattern keeps working: the standard account entrypoint and its signed `AppPayload` with a `tx_nonce`, the `#[authorize_once]` style nullifiers, authorisation witnesses and their consumer-side nullifiers, fee-payment contracts, and the multi-call entrypoint. None of these reads the protocol nullifier, and none is invalidated by its new derivation. The change is the protocol-level foundation for account contracts and authwits to optionally bind signed intents to the transaction they authorise; adopting that is optional framework work that can land separately and incrementally.

**aztec-kit and other client libraries.** Request building, signing, fee handling and simulation continue unchanged. Libraries that add their own replay or cancellation machinery keep it and can retire it at their own pace once they choose to rely on the protocol nullifier instead.

**Infrastructure providers (explorers, indexers, nodes).** The value of a transaction's first nullifier is derived differently. No node component recomputes it from the tx request; nodes only read it from kernel outputs. Nothing known breaks. Nodes and mempools SHOULD be aware that two pending transactions can legitimately share a nullifier (see [Security Considerations](#security-considerations)).

**Sequencers and provers.** Every private-kernel verification key, and therefore the protocol's verification-key tree root, changes. Rollup circuits, the AVM and L1 contracts are untouched. Client-side proving cost is unchanged to first order: the init kernel hashes four fields instead of fifteen.

## Motivation

Users of any transactional system expect three properties of a submitted transaction:

1. **Replay protection.** A transaction, or an authorisation over it, cannot be included twice.
2. **Fee bumping.** A transaction stuck in the mempool can be resubmitted with a higher fee, and only one of the two versions can be mined.
3. **Cancellation.** A pending transaction can be superseded by a cheaper or empty transaction, and again only one of the two can be mined.

On Ethereum all three follow from the account nonce. Aztec has no public per-account nonce, by design: private accounts must not publish a counter. What Aztec does have is a nullifier that every transaction emits and that the chain rejects if it repeats. That nullifier is the natural carrier for these properties, but only if its preimage is chosen so that a bump or a cancellation produces the *same* nullifier as the original. The previous definition, `H(tx_request)` over all fifteen fields, does the opposite: changing the gas price or the first call's arguments changes the nullifier, so a bump and its original can both be mined.

Without a suitable protocol nullifier, accounts must emit a second, application-defined nullifier to obtain these properties. That costs a nullifier per transaction, must be designed and audited per account implementation, and has been the source of a cluster of authorisation bugs. Narrowing the protocol nullifier's preimage gives every account the property for free and lets application-level machinery be simplified later.

The Faerie-Gold role of the protocol nullifier is unaffected: it must merely be unique per mined transaction, which any chain-rejected nullifier is.

## Specification

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119 and RFC 8174.

### Definitions

The tx request is the structure a wallet hands to the private kernel to describe a transaction:

| Field | Type | Meaning |
| --- | --- | --- |
| `origin` | `AztecAddress` | Contract address of the first call |
| `args_hash` | `Field` | Hash of the first call's arguments |
| `tx_context.chain_id` | `Field` | Chain the transaction is for |
| `tx_context.version` | `Field` | Rollup version the transaction is for |
| `tx_context.gas_settings` | 8 fields | Gas limits, teardown limits, max fees, max priority fees |
| `function_data` | 2 fields | Function selector and privacy flag of the first call |
| `salt` | `Field` | The transaction nonce, drawn by the wallet |

`H_d(xs)` denotes `poseidon2_hash_with_separator(xs, d)`, the protocol's existing Poseidon2 hash of the field sequence `[d, ...xs]`.

`NULL_MSG_SENDER` is the reserved address `p - 1` (the field modulus minus one), which no deployed contract can have.

### Domain separator

A new domain separator MUST be used:

| Constant | Decimal value | Derivation |
| --- | --- | --- |
| `DOM_SEP__PROTOCOL_NULLIFIER` | 4023616154 | `poseidon2_hash_bytes("az_dom_sep__protocol_nullifier")` reduced to `u32`, per the protocol's existing separator scheme |

The separator `DOM_SEP__TX_REQUEST` (3763737512), whose only use was the previous derivation, is removed.

### Protocol nullifier derivation

The unsiloed protocol nullifier value MUST be:

```text
protocol_nullifier_value = H_PROTOCOL_NULLIFIER([origin, chain_id, version, salt])
```

The value that enters the nullifier tree MUST be that value siloed under the reserved address, using the protocol's existing nullifier siloing:

```text
protocol_nullifier = H_SILOED_NULLIFIER([NULL_MSG_SENDER, protocol_nullifier_value])
```

`args_hash`, `gas_settings` and `function_data` MUST NOT be part of either preimage.

### Kernel behaviour

The following rules are unchanged by this AZIP and are restated because the definition above depends on them.

1. The init kernel MUST insert a nullifier with value `protocol_nullifier_value`, `note_hash = 0`, side-effect counter 1, scoped to `NULL_MSG_SENDER`, at index 0 of the transaction's nullifiers. No other side effect may use counter 1, so this nullifier is non-revertible and sorts first.
2. The init kernel MUST validate the first call against the full tx request: `origin` equals the call's contract address, `function_data` equals the call's function data, `args_hash` equals the call's argument hash, and `tx_context` equals the call's transaction context. The proof therefore remains pinned to every field of the request, including the fields that leave the nullifier preimage.
3. The reset kernel MUST silo the nullifier as it siloes every other nullifier, producing `protocol_nullifier`.
4. Note nonces MUST continue to be derived from the siloed first nullifier: for the note at index `i` in the transaction, `nonce_i = H_NOTE_HASH_NONCE([protocol_nullifier, i])`, and the unique note hash is `H_UNIQUE_NOTE_HASH([nonce_i, siloed_note_hash])`.

### Uniqueness semantics

Because the nullifier tree rejects duplicates, any two transactions whose tx requests agree on `(origin, chain_id, version, salt)` are mutually exclusive: at most one of them can ever be mined. This holds regardless of their gas settings, first-call function or arguments, or anything they do.

### Salt requirements

- A wallet MUST draw the salt uniformly at random from the field for every transaction it intends to be independent of every other transaction from the same origin.
- A wallet MAY reuse the salt of a pending transaction, from the same origin, chain and version, when it intends the new transaction to supersede the pending one. Which of the two is mined is decided by block builders.
- The kernel MUST NOT reject a salt on the basis of its value. In particular a zero salt MUST be accepted: the kernel cannot verify entropy, and rejecting one degenerate value would give false assurance. Clients SHOULD warn when a salt is zero, since zero is what an unset field looks like.

### Exposure to application circuits

The kernel MUST NOT expose the raw salt to application circuits. What application circuits may see of the transaction's identity is the siloed `protocol_nullifier`, which is public on chain in any case. (The mechanism by which it is exposed replaces an earlier field and is a bug fix outside this AZIP's scope.)

## Rationale

**Why these four fields.** The preimage is the smallest set that gives the intended semantics. `salt` is the nonce. `origin` scopes the nonce to the contract that begins the transaction, so that a salt known to one party cannot exclude a transaction from a different origin. `chain_id` and `version` prevent a nullifier from being meaningful on another chain or rollup version, matching the existing replay domains of the tx context.

**Why gas settings and the first call leave the preimage.** A fee bump changes gas settings and nothing else; a cancellation changes the first call, possibly to a no-op. Both must produce the original's nullifier, so neither gas nor intent can be in the preimage. Pinning the proof to those fields is the init kernel's job, and it still does it.

**Why keep `origin`.** Two designs were considered: with `origin` in the preimage (adopted) and without it. Without `origin`, anyone who learns a salt, for instance a malicious wallet that built the original transaction, could submit a transaction of their own with the same salt and, if the builder prefers it, prevent the original from ever being mined. With `origin`, a competing transaction must start at the same contract; for an account contract that means passing that account's authorisation. The cost is that a transaction whose first call is a fee-payment contract must be cancelled through that fee-payment contract, which such contracts are expected to support.

**Why not a second, application-level nullifier.** Emitting an account-defined nullifier keyed on an account nonce gives the same properties, at the cost of one extra nullifier per transaction and of every account implementation getting the design right. The protocol already emits one nullifier per transaction; giving it these semantics is strictly cheaper and uniform across accounts.

**Why not a sequential nonce.** An Ethereum-style counter requires readable per-account state. Aztec accounts are private, cannot publish a counter, and would lose the ability to have several transactions in flight at once. A random nonce committed by a nullifier gives replay protection and mutual exclusion without either.

**Why the value is unpredictable.** The salt is a uniformly random field element. An observer who does not know it cannot recompute the nullifier from the public `origin`, `chain_id` and `version`, so a nullifier cannot be linked to its origin by dictionary attack. This was the salt's original purpose and it is retained.

**Why the kernel does not check the salt.** A check for `salt != 0` would be theatre: a salt of 1, or any low-entropy value, is exactly as bad and cannot be detected. Freshness is a wallet obligation, stated here as such.

## Backwards Compatibility

This is a breaking change to the private kernel circuits and MUST activate with a new rollup version. Every private-kernel verification key and the verification-key tree root change. Old and new kernels MUST NOT be mixed in a proof chain.

The transaction hash is unchanged in definition: it is computed over the tail kernel's public inputs, not over the tx request. The rollup circuits, the AVM, L1 contracts, the transaction pool and block building are unchanged. The genesis header and the protocol contracts' class identifiers are unchanged.

### Existing client paradigms are unaffected

No Aztec.js, Aztec.nr, PXE or aztec-kit paradigm is broken by this AZIP, and none becomes impossible. Concretely:

- Wallets that draw a random salt per transaction, which is the behaviour of the reference client, need no change.
- Account contracts that authorise a signed payload carrying their own nonce, and emit their own nullifier for it, keep doing so. Their replay protection is unaffected; it now sits alongside the protocol's, rather than replacing it.
- Authorisation witnesses, their consumer-side nullifiers, and the `#[authorize_once]` pattern are unchanged.
- Fee-payment contracts and multi-call entrypoints are unchanged.
- The PXE's simulation, note handling and proving flows are unchanged apart from computing the first nullifier by the new formula.

The properties this AZIP makes available at the protocol level (tx-bound authorisation, fee bumping and cancellation through the protocol nullifier alone, fewer application nullifiers) are opt-in. Each account implementation, wallet or library can migrate to them independently and over time. The old and new approaches can coexist on the same chain and even inside the same transaction. No flag day is required.

Fixture and test data that hard-code a transaction's first nullifier, or note nonces derived from it, must be regenerated.

## Test Cases

Implementations MUST reproduce the following vector, which is asserted in both the Noir and TypeScript reference implementations:

| Input | Value |
| --- | --- |
| `origin` | 1122 |
| `args_hash` | 33 |
| `chain_id` | 44 |
| `version` | 55 |
| `gas_settings` | limits (2, 2), teardown limits (1, 1), max fees (4, 4), max priority fees (3, 3) |
| `function_data` | selector 66, `is_private = true` |
| `salt` | 789 |

| Output | Value |
| --- | --- |
| `protocol_nullifier_value` | `0x274bc3bf8d36c9c8628a471d930d1d833dd5072df6fe108390f04f7d88418051` |
| `protocol_nullifier` (siloed) | `0x032db509ef1efc8cdefdab5e059061d52e1b04aaccc04404f87d0bef7d0021e1` |

Conformance tests MUST additionally cover:

1. Changing `gas_settings` or `args_hash` leaves both outputs unchanged.
2. Changing any one of `salt`, `origin`, `chain_id` or `version` changes both outputs.
3. The nullifier the init kernel inserts at index 0, once siloed by the reset kernel, equals `protocol_nullifier` computed directly from the tx request.
4. The init kernel rejects a first call whose `origin`, `function_data`, `args_hash` or `tx_context` differ from the tx request, and rejects a tx request whose salt differs from the one the first call was proven against.
5. Two transactions from the same origin with the same salt but different gas settings produce identical first nullifiers.

## Reference Implementation

[aztec-packages PR #25515](https://github.com/AztecProtocol/aztec-packages/pull/25515), pinned at [999b0558](https://github.com/AztecProtocol/aztec-packages/commit/999b055823096c194094ebd8b28ed63ef10df3c9), implements the derivation in `TxRequest::compute_protocol_nullifier_value` and `TxRequest::compute_protocol_nullifier` in the protocol circuits' `types` crate, and the corresponding `computeProtocolNullifierValue()` / `computeProtocolNullifier()` on the TypeScript `TxRequest`. Its client patch updates the PXE to derive the value once per transaction and seed the simulated note nonces from it.

## Security Considerations

**Threat model.** The parties are a user, the wallet that builds the user's transactions, other applications whose circuits run inside the transaction, block builders, and observers of the mempool and chain. All except the user may be malicious.

**Faerie-Gold protection is preserved.** Note nonces derive from the siloed first nullifier, which the tree rejects if repeated, so note nonces remain unique across the chain exactly as before. The change is only to which inputs the nullifier commits to.

**Salt entropy is the wallet's responsibility.** A wallet that reuses a salt unintentionally makes its own transactions mutually exclusive: the first is mined, the rest fail with a duplicate nullifier. A wallet that uses a guessable salt lets an observer confirm that a given origin produced a given transaction, by recomputing the nullifier. Neither can be detected by the kernel. Wallet implementers MUST treat the salt as a per-transaction secret nonce drawn from a cryptographically secure source. The reference client already does; it also warns on a zero salt.

**A leaked salt.** Knowledge of a pending transaction's salt lets the holder build a competing transaction from the same origin. For an origin that requires authorisation to be called, such as an account contract, the holder still needs that authorisation. For an origin that anyone may call, the holder can produce a competing transaction and, if a builder prefers it, exclude the original; the effect is limited to that one transaction. The kernel does not reveal the raw salt to application circuits, so the parties that can learn it are the wallet and whoever the wallet tells.

**Mutual exclusion is decided by builders, not by the protocol.** When two transactions share a nullifier, the protocol guarantees only that at most one is mined. Which one is chosen by the block builder that includes it; a builder is expected to prefer the higher-paying transaction but is not obliged to. A user who cancels a transaction must treat the cancellation as best-effort until a block confirms which transaction landed. This is the same guarantee Ethereum gives for replacement transactions.

**Mempool behaviour.** The reference node's double-spend validation rejects a transaction whose nullifiers already exist in the tree, and one that repeats a nullifier within itself, but does not compare pending transactions with one another. Two transactions sharing a protocol nullifier can therefore both sit in the mempool; the loser fails at block building. Node implementers MAY add replacement policies (for example, keep the higher-fee one) as a client-side optimisation. Any such policy MUST NOT drop a transaction on the basis of its protocol nullifier alone without the replacement being valid, or it becomes a censorship vector.

**Domain separation.** The new separator distinguishes the protocol nullifier value from every other protocol hash, and the reserved `NULL_MSG_SENDER` silo distinguishes it from every application nullifier. An application cannot produce a nullifier that collides with a protocol nullifier.

**No new trust in the wallet.** The wallet already chooses every field of the tx request and already holds the salt. This AZIP gives the salt semantics without widening what the wallet can do.

## Copyright Waiver

Copyright and related rights waived via [CC0](/LICENSE).
