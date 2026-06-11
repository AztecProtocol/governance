# Aztec Improvement Proposal: Fungible Token

## Preamble

|azip|title|description|author|discussions-to|status|category|created|requires|
|-|-|-|-|-|-|-|-|-|
|18|Fungible Token|An interface for fungible tokens|TBD|TBD|Draft|Standard|2026-06-11|AZIP-11|

## Abstract

The following standard defines an interface for fungible tokens in Aztec.
Balance is split into private and public balances, and transfer functions are defined within each scope and across the boundary.
Transferring on behalf of another party is attained via an authorization mechanism over the transfer function, e.g. as defined in [AZIP-11](./azip-11.md).

## Impacted Stakeholders

All applications that use fungible tokens: market making, lending protocols, payments, etc.

## Motivation

A standard interface for fungible tokens enables the construction of an ecosystem that requires the composable exchange of assets.

## Specification

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC-2119 and RFC-8174.

The following describes the interface for a "fungible token" contract.
Tokens MUST implement all of the functions described below.

### Constants

**`PRIVATE_ADDRESS_MAGIC_VALUE: AztecAddress = AztecAddress::from_field(poseidon2_hash_bytes("az_private_address_magic_value".as_bytes()))`**: Special address value representing an unknown party in the `Transfer` event.

### Authorization nonce

Several external methods described here take an `authorization_nonce: Field`. This value is consumed by the authorization check (e.g. as defined in [AZIP-11](./azip-11.md)) to bind and disambiguate authorizations. Callers SHOULD use a random value.

### Private and public balance

Tokens MUST keep track of two separate balances per address:
- Public, queryable by anyone
- Private, queryable by knowing the corresponding notes

### Commitment

Tokens MUST define a commitment scheme whereby a recipient address `to` can be committed into a `commitment: Field`, domain separated from other kinds of commitments. It MUST be possible for the token to construct a conventional note from the `commitment` and an `amount: u128`, owned by `to`.

#### initialize_transfer_commitment

```rust
#[external("private")]
fn initialize_transfer_commitment(to: AztecAddress, completer: AztecAddress) -> Field;
```

Prepares a commitment and returns its value.

If `completer` is non-zero, the commitment MUST enforce `completer` as the sender in the transfer functions defined below.
Otherwise, the commitment MUST NOT enforce any completer.

If the token cannot initialize the requested kind of commitment, this function MUST revert.

Off-chain commitments MUST be obtained by simulating a call to `initialize_transfer_commitment` with a zero `completer`.

### Private state data availability

Tokens MUST ensure all data relevant to an address' private balance is emitted via private logs encrypted to the owner, so that total private balance is recoverable from Aztec's private logs via trial decryption.

Encrypted logs SHOULD be tagged according to the de-facto sender-recipient tagging scheme.

### Token data

The values returned by `name`, `symbol` and `decimals` MUST be constant for the lifetime of the contract.

**`FieldCompressedString`**: a string of at most 31 UTF-8 bytes compressed into a single `Field`. The bytes, right-padded with zero bytes to a length of 31, are interpreted as a big-endian unsigned integer.

#### name

Returns the name of the token - e.g. `"MyToken"`.

```rust
#[external("public")]
#[view]
fn name() -> FieldCompressedString;
```

#### symbol

Returns the symbol of the token. E.g. `"BRUH"`.

```rust
#[external("public")]
#[view]
fn symbol() -> FieldCompressedString;
```

#### decimals

Returns the number of decimals the token uses - e.g. `8`, means to divide the token amount by `100000000` to get its human-readable representation.

```rust
#[external("public")]
#[view]
fn decimals() -> u8;
```

### Balances

#### total_supply

Returns the total token supply, from both private and public balances. Any operation that creates or destroys private or public balance (e.g. minting or burning, if the token implements them) MUST update the total supply under constraint.

```rust
#[external("public")]
#[view]
fn total_supply() -> u128;
```

#### balance_of_public

Returns the public balance of account with address `owner`.

```rust
#[external("public")]
#[view]
fn balance_of_public(owner: AztecAddress) -> u128;
```

#### balance_of_private

Returns the private balance of account with address `owner`.

```rust
#[external("utility")]
unconstrained fn balance_of_private(owner: AztecAddress) -> u128;
```

### Transfer methods

Tokens MUST implement all of the methods matching the following shape
```rust
#[external("$domain")]
fn $name(from: AztecAddress, $to, amount: u128, authorization_nonce: Field);
```
according to the following table
| name | to | domain | origin balance | target balance | sender known by | recipient known by | emits transfer event | event `from` | event `to` |
| - | - | - | - | - | - | - | - | - | - |
| transfer_private_to_private | to: AztecAddress | private | private | private | recipient | sender | no | - | - |
| transfer_private_to_public | to: AztecAddress | private | private | public | no-one | everyone | yes | magic value | `to` |
| transfer_private_to_commitment | commitment: Field | private | private | private | recipient | commitment constructor | no | - | - |
| transfer_public_to_private | to: AztecAddress | private | public | private | everyone | sender | yes | `from` | magic value |
| transfer_public_to_public | to: AztecAddress | public | public | public | everyone | everyone | yes | `from` | `to` |
| transfer_public_to_commitment | commitment: Field | public | public | private | everyone | commitment constructor | yes | `from` | magic value |

Tokens MUST deduce the balances from the sender's private or public balance according to "origin balance", and increase the recipient's private or public balance according to "target balance".

The functions MUST revert if any of the following holds:
- The sender hasn't authorized the transfer.
- The sender doesn't have enough balance of the kind prescribed by "origin balance".

Authorization SHOULD be done as described in [AZIP-11](./azip-11.md) with `from` as the approver.

They SHOULD NOT give away information that lets actors deduce the sender or recipient more than prescribed by the columns "sender known by" and "recipient known by".
These columns are upper bounds over the whole flow, including the commitment initialization where applicable; "commitment constructor" denotes the actor that called `initialize_transfer_commitment`.

The "emits transfer event" column instantiates the emission rule described in the [Events](#events) section, and the "event `from`" and "event `to`" columns prescribe the field values of the emitted event, where "magic value" stands for `PRIVATE_ADDRESS_MAGIC_VALUE`.
Transfers of 0 amount MUST be treated as normal transfers.

Functions transferring to a commitment MUST complete the commitment with the amount.
They MUST enforce that the sender match the completer, if one was defined in `initialize_transfer_commitment`.
Off-chain commitments MAY be completed multiple times; each completion creating a distinct note for the committed recipient.

Tokens MAY disallow initializing a commitment and completing it through `transfer_private_to_commitment` within the same transaction.

*Note*: The domain of `transfer_public_to_private` is private, so as to conceal the recipient. The function has to enqueue a public update of the sender's balance.

### Events

#### Transfer

```rust
#[event]
struct Transfer {
    from: AztecAddress,
    to: AztecAddress,
    amount: u128,
}
```

SHOULD be emitted publicly on every balance-changing operation that's publicly inferrable, and SHOULD NOT be emitted on operations that are not.

Whenever either `from` or `to` must not be made publicly available, it MUST take the value `PRIVATE_ADDRESS_MAGIC_VALUE`.

Operations with no sender or no recipient (e.g. mints and burns, if the token implements them) SHOULD use the zero address for the missing party.

## Rationale

### Private address magic value

This is a value that means "unknown address". It has been chosen in contrast with e.g. `0x0`, which is historically used for mint and burn operations, in tokens that have such functions.

### Recipient commitments

The capability of committing to a recipient, and later being able to complete a note allows privately enqueueing a private transfer in a public function without revealing the recipient. As an example, an AMM performing exact-out may need to give change back to the user, but the exact value will only be known during public execution.

The current de-facto commitment scheme (`PartialUintNote`) enforces the definition of a completer during commitment initialization, which is enforced at completion time. This is done in order to prevent completion from being front-run, and to avoid denial-of-service on note discovery.

We've deviated from it on the grounds that future implementations may feature off-chain commitments, by which a recipient may construct a commitment off-chain and hand it to a third party off-band.

The presented standard is compatible with both flows by taking the completer as an explicit parameter of the initialization function: a non-zero `completer` requests a completer-enforcing commitment, while a zero value requests one that anyone can complete. Completer enforcement relies on state recorded when initialization is executed on-chain, which off-chain commitments by definition lack, so the off-chain flow can only use commitments without a completer.

A token may support both kinds through a per-commitment choice, e.g. reserving a bit of the commitment to represent whether completion checks for the nullifier emitted during initialization. Tokens that support a single kind revert on requests for the other.

The commitment's shape is not standardized to allow for different commitment schemes, and thus consumers are required to simulate the commitment initialization function in order to obtain its value.

### String types

The choice of `FieldCompressedString` limits strings (the token's name and symbol) to 31 characters. The length is enough for reasonable use cases, and fitting it into a `Field` makes it easy and cheap to store, retrieve, and use in logs.

Both a larger fixed-size type or a variable-size string would be more expensive without a good enough benefit.

### Constant token data

Consumers cache token metadata and bake `decimals` into amount arithmetic; a token whose metadata changes after deployment silently breaks integrations. ERC-20 leaves this unspecified and immutability exists there only as a convention. This standard makes it a requirement instead.

### Public supply

An alternative design also included a `public_total_supply` function, which would allow indexers to easily fetch the public supply. This is dropped out of the standard since it is not a crucial interface method.

Requiring supply updates under constraint also means every supply change is public: a conformant token cannot conceal mint or burn amounts.

### Transfer methods

The 6 transfer methods are all of the combinations for the origin (private or public) and the target (private, public, or commitment). Having one distinct function for each, rather than boolean arguments, is simplest and reduces proving costs.

While ERC-20 has two ways in which they react to failure (either return `false` or revert), this standard uses only reverts for the following reasons:
- It gives developers an unambiguous interface.
- It guarantees that cross-domain transfers (`transfer_private_to_public`, `transfer_public_to_private`) either succeed or the transaction reverts as a whole.

Note constraining is enforced at the expense of performance. Otherwise, contracts that expect to receive encrypted notes asynchronously as part of their inner working may brick or be griefed. It also guarantees note recoverability. Note that the de-facto partial note implementation emits its logs unconstrained and does not satisfy this requirement.

On the other hand, note *delivery* (via tagging) is not constrained, as it's currently not enforceable.

### Authorization nonce

Requiring a zero nonce when the caller is the sender hurts composability. E.g., a token vault's logic contract may transfer on behalf of a user (non-zero nonce) and afterwards from itself (zero-nonce), requiring the specification of two distinct nonces for the same operation.

### Interface detection

No mechanism for declaring or detecting compliance (à la ERC-165) is specified. Calls are resolved against the contract class at simulation time, so a missing function fails fast at simulation rather than silently misbehaving on-chain.

### Minting and burning

Minting and burning are left out of the standard, as tokens don't necessarily make use of those functions.

### Event emission

The emission of events is not a hard requirement, since it's just an aid for indexing.

## Security Considerations

### Revert on failure

Reversion on failure implies failed transfers cannot be caught in private. Consumers should avoid placing private-side transfer operations in liveness-critical paths, and should favor pull over push operations (individual "claim" functions, rather than batched "distribute" functions).

The same principle applies in public but, since reverts can be caught in public, consumers may catch transfer failures if unavoidable by design.

### Invalid commitments

A commitment is an opaque value whose validity cannot be checked by anyone but its constructor. For commitments without a completer, transferring to a commitment received from another party (e.g. in the off-chain flow) destroys the sender's balance if the commitment is invalid, with no in-circuit way to detect it beforehand. For commitments with a completer, an invalid commitment fails the completer check and the transfer reverts instead.

### Unwanted commitment completion

A commitment that doesn't enforce a completer can be completed by anyone. This means a successful completion doesn't imply the intended completer was the one to do it. E.g., a recipient expecting a certain payment from a commitment cannot assume a failed payment after an insufficient payment has been performed. It requires the definition of a time window throughout which the recipient is going to wait for the commitment's completion.

### Note delivery

The lack of constraints on note delivery (tagging) allows, in principle, the griefing of a user.

It's practically amendable, however:
- If the user has spent a resource, they can ultimately keep track of the note representing said resource, and trial-decrypt over the TX where said resource is spent.
- If the user hasn't spent a resource, they have nothing to lose.

### Reentrancy on authorization

Whenever authorization code is not trusted (such as a sender's `verify_private_authorization`), reentrancy protection measures must be taken, such as performing a static call or the checks-effects-interactions pattern.

### Privacy

Pure private operations (those that don't emit a `Transfer` event) reveal only generic transaction metadata. Every other transfer operation is subject to data analysis (even if the token design chooses not to emit an event).

## Backwards Compatibility

This AZIP requires no protocol changes. However, the current de-facto partial note implementation is non-conformant: it emits its encrypted logs unconstrained, and it rejects zero-amount completions in public. Tokens built on it are non-conformant until it offers constrained delivery and zero-amount completion.

## Test Cases

### Constant values

| constant | value |
| - | - |
| `PRIVATE_ADDRESS_MAGIC_VALUE` | `0x0c827fc5860fb431d8843067db63e0c0623600d48cb2648f1c0d05e8ca5eccfe` |

### FieldCompressedString encoding

| string | encoded value |
| - | - |
| `"BRUH"` | `0x42525548000000000000000000000000000000000000000000000000000000` |

## Copyright Waiver

Copyright and related rights waived via [CC0](/LICENSE.md).
