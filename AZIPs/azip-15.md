# Aztec Improvement Proposal: Aztec Namespace

## Preamble

| `azip` | `title` | `description` | `author` | `discussions-to` | `status` | `category` | `created` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 15 | Aztec Namespace | Define a Chain Agnostic Namespace for Aztec | Paperclip Minimizer (@paperclip-minim) | https://github.com/AztecProtocol/governance/discussions/38 | Draft | Standard | 2026-05-22 |

## Abstract

We define a Chain Agnostic namespace and profiles for CAIP-2, CAIP-10, and CAIP-350. This results in an unambiguous definition of Aztec chain ID for every Aztec deployed version across all EVM blockchains, and an interoperable address that includes Aztec addresses along with a specific rollup version.

## Impacted Stakeholders

Every stakeholder that receives user input (bridges, wallets, dApps) as well as on-chain applications dealing with cross chain messages, may unequivocally identify Aztec address-blockchain pairs, including senders, recipients, and tokens. They'll also have routing information (settlement chain and rollup contract address) available.

## Motivation

This is a first step towards making Aztec rollups available for ERC-7683 (a cross-chain intents standard), as well as the open-intents framework. Cross-chain messaging *requires* a definition of chain ID for every involved chain. E.g., an intents-based bridge requires representing the chain for the input assets, as well as each output's recipient, which may be any address at any supported chain.

Separately, this allows for a definition of addresses that are bound to a specific rollup, so that they brick if they're used for an incompatible Aztec rollup version. Aztec's address derivation is deterministic in the contract's constructor arguments, its function bytecode and verification keys, and the account's public keys. This scheme is not guaranteed to hold constant across different Aztec versions, which means the same address that a user controls in one rollup version may not be controllable by the user in a different version. Inadvertently sending funds to an address for a newer rollup version may result in loss of funds.

## Specification

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119 and RFC 8174

The chain-agnostic namespace `aztec` SHALL be reserved for the Aztec ecosystem. And the following ChainAgnostic profiles SHALL be pushed into Chain Agnostic's namespaces repo.

- [CAIP-2](../assets/azip-15/caip-2.md): defines a blockchain ID
- [CAIP-10](../assets/azip-15/caip-10.md): defines a text representation for account addresses
- [CAIP-350](../assets/azip-15/caip-350.md): specifies text and binary representations of the chain ID and account address, plus a 2-byte chain type identifier.

A brief description of those is included in the subsections below.

### CAIP-2

This profile specifies a unique chain ID for every chain, restricted to match the regex `[-_a-zA-Z0-9]{1,32}`. Since Aztec rollup contracts compile to EVM bytecode, every live Aztec rollup chain has an associated EVM chain ID and rollup contract address.

An Aztec chain's ID is defined as a hash of the settlement chain's ID and the rollup contract address. Optionally, a chain may also have a Governance-attributed human-readable name.

The alias is stored in a Governance-owned registry, as described in the [chain registry](#chain-registry) section; the hash form is computable offline from `(evmChainId, rollupContractAddress)`, but the same registry exposes it canonically and provides reverse lookup. An Aztec chain's CAIP-2 chain ID can be queried by calling the registry's `getTextChainId` method.

Clients SHOULD resolve a chain's CAIP-2 chain ID by querying a node of that chain via a dedicated JSON-RPC method (e.g., `aztec_getChainId`). Nodes derive the chain ID by reading the alias from the on-chain registry if one is set, or otherwise computing the hash form locally from the known `evmChainId` and `rollupContractAddress`.

#### Human-readable form

For every existing chain, governance MAY choose to bind a human-readable name once and irreversibly, by calling the registry's `setAlias` method. Said form will be restricted to strings matching the regex `[_a-z]{1,31}`. As an opt-out, the alias MAY instead be set to the chain's deterministic text chain ID, which locks the chain as non-aliasable.

#### Hash of the chain's details

Define `binary_chain_hash = keccak256(abi.encodePacked(evmChainId, rollupContractAddress))[:23]`, where
- `evmChainId` is a `uint256` holding the settlement chain's EVM chain ID.
- `rollupContractAddress` is the `address` of the rollup contract on the settlement chain.

Then, the chain ID's CAIP-2 representation is the base58btc encoding of `binary_chain_hash`, left-padded with `'1'` characters (base58btc's zero) to exactly 32 characters.

### CAIP-10

This profile specifies a text representation for Aztec addresses, restricted to match the regex `[-.%a-zA-Z0-9]{1,128}`. We'll define it as the 0-padded 64-character hexadecimal representation of the `AztecAddress`, with the mixed-case Aztec-chain-dependent checksum inspired by EIP-55 as described:

Define `non_checksummed_aztec_address` as the lower-case 0-padded 64-character hexadecimal representation of the `AztecAddress`'s inner `Field` element. Then, the checksummed CAIP-10 Aztec address is constructed by, for each `i` in `0..64`, upper-casing the `i`-th character of `non_checksummed_aztec_address` if and only if the `i`-th bit of `binary_chain_hash` is `1`. Numeric characters are left unchanged.

Consumers of this standard MUST validate the checksum.

### CAIP-350

This profile specifies three representations for both the chain ID and the address:
- Customary representation: whatever the ecosystem uses.
- Text representation: this is like CAIP-2, but without a character limit.
- Binary representation: matching EIP-7930's binary format

As well as a 2-byte binary key representing the chain type.

The `aztec.on.eth` subdomain SHALL be registered, and when `on.eth` allows custom ownership of its subdomain, it SHALL be owned by the Governance contract.

When an interoperable name omits the chain (e.g., `<address>@aztec`), the Aztec chain pointed to by `aztec.on.eth` is used to compute and validate the address's checksum.

#### Chain type

The chain type is a 2-byte value, uniquely associated to the namespace.

This AZIP proposes `0xa27c`, which reads almost like "Aztec".

#### Customary and text representation

Both chain ID and address representations match CAIP-2 and CAIP-10.

#### Binary representation

Chain ID MUST be `binary_chain_hash` defined in the [CAIP-2 section](#caip-2).

When consumed by protocols that expect a fixed-width 32-byte chain ID (e.g., current OIF code), `binary_chain_hash` MUST be left-padded with `0x00` to 32 bytes. Its `uint256` form is the standard EVM big-endian interpretation of those 32 bytes (equivalently, of `binary_chain_hash` left-padded with zeros).

For the address, this is just the Ethereum `uint256` for the field number in the `AztecAddress`.

### Chain registry

A chain registry MUST be deployed, MUST inherit from OpenZeppelin's `Ownable`, and MUST be owned by the Governance contract.

It MUST implement the following methods:

```solidity
function getTextChainId(uint256 evmChainId, address rollupContractAddress) external view returns (string memory);
```

Returns the text representation of the chain ID for the Aztec chain represented by the arguments. It MUST return the human-readable form if available, and the hash form otherwise. Clients that need the binary form decode the result as base58btc (stripping leading `'1'` padding) when the length is 32; otherwise (i.e., when an alias was returned) they MUST resolve the underlying `(evmChainId, rollupContractAddress)` via `getChainDetails` and then either call `getBinaryChainId` or recompute the hash locally.

```solidity
function setAlias(uint256 evmChainId, address rollupContractAddress, string calldata alias) external onlyOwner;
```

Sets `alias` as the human-readable chain ID for the Aztec chain represented by the arguments.
MUST assert that:
- `alias` matches the regex `[_a-z]{1,31}` *or* is equal to the text chain ID deterministically derived from the chain's information, in which case it becomes non-aliasable.
- `alias` hasn't been assigned to another Aztec chain before.
- `setAlias` hasn't been successfully called for this Aztec chain before.
- At least one of the following holds:
  - `evmChainId` is not `1`
  - a static call to `rollupContractAddress`'s `owner()` method returns the registry owner's address
  - `ensureAlias` has been successfully called before with `alias` matching the value passed here
MUST store the chain details for the deterministic chain ID as well.
MUST emit an `AliasSet` event.

```solidity
function ensureAlias(address rollupContractAddress, string calldata alias) external;
```

Pins `alias` as the only human-readable form that governance is allowed to bind to the Aztec chain settling at address `rollupContractAddress` on Ethereum mainnet.
MUST assert that:
- `alias` matches the regex `[_a-z]{1,31}` *or* is equal to the text chain ID deterministically derived from the chain's information, in which case it becomes non-aliasable.
- `msg.sender` matches the one returned by a static call to `rollupContractAddress`'s `owner` method.
MUST NOT check that `alias` hasn't been assigned to another chain, and MUST allow later calls to overwrite the previous ensured alias.
MUST emit an `AliasBound` event.

```solidity
function getChainDetails(string calldata textChainId) external view returns (uint256, address);
```

When it has been stored either via `setAlias` or `storeChainDetails`, returns the corresponding EVM chain ID and rollup contract address for the Aztec chain with text chain ID `textChainId`.

```solidity
function storeChainDetails(uint256 evmChainId, address rollupContractAddress) external;
```

Store the EVM chain ID and rollup contract address (the *details*) for the chain ID corresponding to said chain.
MUST be permissionless.
MUST ensure the chain details haven't been stored before.
MUST emit a `ChainDetailsStored` event.

```solidity
function getBinaryChainId(uint256 evmChainId, address rollupContractAddress) external pure returns (bytes23);
```

Returns the binary representation of the chain ID, `binary_chain_hash` as defined in the [CAIP-2 section](#caip-2). Although callers can compute this locally, the registry exposes it as a normative reference so that consumers do not produce divergent encodings.

It MUST define the following events:

```solidity
event AliasSet(uint256 indexed evmChainId, address indexed rollupContractAddress, string alias);
```

Emitted by `setAlias` when governance binds a human-readable `alias` to the Aztec chain identified by `evmChainId` and `rollupContractAddress`.

```solidity
event AliasBound(address indexed rollupContractAddress, string alias);
```

Emitted by `ensureAlias` when the chain owner pins `alias` as the only human-readable form acceptable for the Aztec chain settling at `rollupContractAddress` on Ethereum mainnet.

```solidity
event ChainDetailsStored(uint256 indexed evmChainId, address indexed rollupContractAddress);
```

Emitted by `storeChainDetails` when the EVM chain ID and rollup contract address backing a chain ID are recorded in the registry, enabling text-to-binary lookups.

#### Constructor

The registry's constructor allows seeding aliases for mainnet-settling Aztec chains without the ownership restrictions enforced by `setAlias`. This MAY be used by governance to give human-readable names to mainnet-settling Aztec chains whose ownership has already been renounced on mainnet at deployment time.

```solidity
constructor(address[] memory rollupContractAddresses, string[] memory aliases);
```

Each entry refers to the Aztec chain settling at `rollupContractAddresses[i]` on Ethereum mainnet (i.e., `evmChainId == 1`).

MUST assert that:
- Both arrays have the same length.
- For each `i`, `aliases[i]` matches the regex `[_a-z]{1,31}` *or* is equal to the text chain ID deterministically derived from `(1, rollupContractAddresses[i])`, in which case that chain becomes non-aliasable.
- No `aliases[i]` is reused for another chain in the constructor call.

MUST emit an `AliasSet` event for each `i`.

After construction, all alias-setting MUST go through `setAlias` and `ensureAlias` with their full constraints.

### Examples

Consider the following two chains:
- Alpha, settling to contract at address `0xAe2001f7e21d5EcABf6234E9FDd1E76F50F74962` on Ethereum mainnet.
- Testnet, currently settling to contract at address `0xf6D0D42aCE06829bECB78C74F49879528fC632c1` on Sepolia.

Assuming
- Alpha is aliased to `alpha_flying_bison`, and pointed to by `aztec.on.eth`.
- Testnet is aliased to `testnet_gravastar`.

Consider an arbitrary Aztec address, `0x9203544e42ba86847CA8458432F7C0265CE567e74064cB25B2a9723C390463C2`.

#### Chain IDs

- Alpha: `alpha_flying_bison`, `2LKN5QVpKjqRxc2KsPM4nMojhvryewCs`.
- Testnet: `testnet_gravastar`, `1DQUdRx75WPNrWmkcyVEyeuu9FQ6tT7x`

#### CAIP-10-style chain-specific addresses

- Alpha
  - `aztec:alpha_flying_bison:9203544e42ba86847CA8458432F7C0265CE567e74064cB25B2a9723C390463C2`
  - `aztec:2LKN5QVpKjqRxc2KsPM4nMojhvryewCs:9203544e42ba86847CA8458432F7C0265CE567e74064cB25B2a9723C390463C2`
- Testnet
  - `aztec:testnet_gravastar:9203544e42bA86847Ca8458432F7c0265cE567E74064cb25B2a9723C390463c2`
  - `aztec:1DQUdRx75WPNrWmkcyVEyeuu9FQ6tT7x:9203544e42bA86847Ca8458432F7c0265cE567E74064cb25B2a9723C390463c2`

Notice the differing mixed-case checksum:
```
                    _      _         _    _    _      _                _
alpha:   9203544e42ba86847CA8458432F7C0265CE567e74064cB25B2a9723C390463C2
testnet: 9203544e42bA86847Ca8458432F7c0265cE567E74064cb25B2a9723C390463c2
```

#### Interop-style chain-specific addresses

- Alpha
  - `9203544e42ba86847CA8458432F7C0265CE567e74064cB25B2a9723C390463C2@aztec`
  - `9203544e42ba86847CA8458432F7C0265CE567e74064cB25B2a9723C390463C2@aztec:alpha_flying_bison`
  - `9203544e42ba86847CA8458432F7C0265CE567e74064cB25B2a9723C390463C2@aztec:2LKN5QVpKjqRxc2KsPM4nMojhvryewCs`
- Testnet
  - `9203544e42bA86847Ca8458432F7c0265cE567E74064cb25B2a9723C390463c2@aztec:testnet_gravastar`
  - `9203544e42bA86847Ca8458432F7c0265cE567E74064cb25B2a9723C390463c2@aztec:1DQUdRx75WPNrWmkcyVEyeuu9FQ6tT7x`

## Rationale

### Using the Chain Agnostic namespace

Chain Agnostic is the dominant standard for cross-chain identifiers and addresses.

CAIP-2 and CAIP-10 are ubiquitous. Out of the 42 namespaces registered as of 2026-05-22, CAIP-2 is present in 41 of them, and CAIP-10 in 26.

CAIP-350 (the foundation for interop) introduces the definition of the *binary* representation, which allows for an on-chain representation. Coupled with an `aztec.on.eth` subdomain registration, this unlocks interop names that look like `<address>@aztec`.

### Chain definition

By binding an Aztec chain ID to pairs of EVM chain ID and contract address, it's implicitly assumed that there's no more information pertaining a chain's definition. E.g., if the rollup contract address is a proxy that gets updated, the chain ID will still be the same.

A further versioning integer could be used, so that changes within the same rollup contract would make the previous chain ID invalid (forever).

Aztec chain changes can be categorized based on whether they affect the meaning of an Aztec address. This could happen, e.g., if the address derivation scheme is changed (as in [AZIP-9](./azip-9.md)), or if either the AVM or the proving system is changed.

Changes that don't change the meaning of Aztec addresses don't affect the validity of recipients by definition. In such a case, a chain ID change would impose an unnecessary migration cost.

In contrast, if a chain update changed the meaning of Aztec addresses, an ensuing change of chain ID would prevent protocols from sending funds to addresses that are now bricked. In the bigger picture, opening up to such possibility would require making portals version-dependent as well, as hardcoded values for e.g. a wrapped token's L1 contract would render them unusable after such a change.

We decided to keep the chain ID constant under such changes on the grounds that when such changes happen, the chain is switched in place much in the same way a non-splitting hard fork does it.

### Chain ID's binary representation

We could've alternatively defined the binary representation of the chain ID as `abi.encodePacked(uint256, address)` (`bytes`, 52 bytes long). An advantage of this is that the EIP-7930 interoperable address would contain all of the routing information required.

However, while OIF-maintained ERC-7683 currently depends on EIP-7930 (and thus was compatible with said definition), the currentl OIF code, as well as related bridges, use `(chain, address)` pairs where the length of both `chain` and `address` is 32 bytes (and disregard the binary key altogether).

We've re-defined the binary chain ID so that it fits in those protocols as well. A positive (but less relevant) consequence is that gas costs are smaller.

The binary representation is limited to 23 bytes so that conversion back and forth between binary and text representation is trivial, and can be done offline.
 
As a downside, the binary chain ID doesn't contain useful information (settlement chain ID and rollup contract address). However, the on-chain registry provides lookup data from binary chain ID to the pre-image.

### Chain ID's text representation

CAIP-2's chain ID is restricted to 32 characters from a character set of 64 characters, which is a total of 192 bits at 6 bits per character. CAIP-350's chain ID's text representation releases this constraint, from `[-_a-zA-Z0-9]{1,32}` to `[.-:_a-zA-Z0-9]*` (see EIP-7828 on interoperable names).

The latter constraint, along with introducing a reasonable limit to chain IDs (2 ** 64), and disregarding human-readable names, would allow for a reasonably-small (~38 characters) bijective representation between text and binary, where both had the complete rollup information.

We decided to constrain the CAIP-350 to be the same as the CAIP-2 representation, in order not to introduce two differing standards for the same task (representing the chain). This would break the bijectiveness between CAIP-350 and CAIP-2 representations.

Within the alphabet permitted by CAIP-2, the hash form is encoded as base58btc. Its alphabet avoids `-`, which breaks double-click word selection in most UIs and terminals.

Within that constraint, four approaches were considered.

#### Hash only (rejected)

A chain's ID is the base58btc encoding of the 23-byte hash (left-padded to 32 chars), with no governance-assigned alternative. Binary-to-text conversion is offline; the on-chain registry's sole purpose is providing the inverse (text-to-binary) lookup for off-chain services' convenience.

Rejected because it leaves no room for short, memorable identifiers for popular chains.

#### Governance-assigned name replaces the hash (rejected)

When governance assigns a human-readable name, that name *becomes* the chain ID and the hash form is no longer valid for the chain.

Rejected because it makes the registry a *requirement* for binary-to-text lookup of any chain that ever gets a name, and forces consumers to deal with a single chain having two different canonical IDs across its lifetime.

#### Hash as canonical, with optional human-readable alias (chosen)

The hash is always a valid chain ID, so binary-to-text conversion is offline by default. Governance MAY additionally assign a human-readable alias, queryable via `getTextChainId` and accepted as an alternative text form for the same chain.

This preserves offline binary-to-text conversion for the default case while still letting popular Aztec chains advertise short, memorable IDs (e.g., `alpha_flying_bison`, with prefixes available to denote development status). The registry lookup cost for resolving an alias is deemed acceptable, since cross-chain interactions already require a functioning network.

The human-readable alias is purposefully limited to one character short of the deterministic derivation in order to prevent governance attacks, as described in the [security considerations](#security-considerations) section.

#### Storing compressed chain ID lookup information (rejected)

The rationales in favour of human-readable names are strong enough to justify discarding this as well, but the following reasons also apply.

We considered using the concatenation of a representation of the settlement chain ID and the contract address.

The full contract address requires 27 base 64 characters, leaving 5 characters for the chain ID, bounding the chain ID to be smaller than `2 ** 30`. While this is a high bound (100x Sepolia's chain ID), it's lower than the currently proposed bound.

Truncating the contract address (by the one character required to reach the bound) in order to expand the chain ID was deemed too cumbersome for data lookup.

Alternatively, we considered compressing the block-number and the truncated TX hash of the deploying TX. This way, lookup could happen by checking known EVM chains at the given block number and looking for the TX whose first bits matched the truncated TX hash. However, this already involves more than one node query, in contrast with the one required via the use of a registry.

### Address representations

Including a checksum dependent on chain ID makes direct substitution of the chain ID invalid.

We considered using a base 64 representation for addresses, with a replacement for `_` (not available for CAIP-10 addresses), or a base58btc representation. This would require approximately 43 characters in contrast to the 64 required for hexadecimal representation. A few more characters could be used to include a checksum that prevented direct replacement of the chain ID in the full specification of chain and address.

We went in favour of the hexadecimal representation with the mixed-case checksum because we believe many UIs (potentially including hardware wallets) will expect hexadecimal for the address, and this would introduce again two standards for the same task. The mixed-case checksum should already prevent just trimming the address, and having the same representation allows people to do quick visual inspection to ensure two addresses are the same.

### Chain registry

We chose to specify a standalone contract to act as a registry instead of bundling into the rollup registry. This avoids a protocol-contract upgrade. Considering that the functionality for the chain registry is only that of documenting, it's simple enough not to merit further upgrades.

The registry is intentionally immutable: off-chain consumers can hardcode its address with confidence that the contract and its semantics will not change.

In order to prevent Governance from assigning names to chains not related to governance, the `ensureAlias` function has been proposed so that the chain owner can request the chain not to be aliased *or* a specific alias for the chain.

Two ways to gate this function have been explored.
1. Allow `ensureAlias` to work over any settlement chain ID. Introduce a `startEnsureAlias` function, which should be called a certain amount of time (e.g. 1 month) before enabling `ensureAlias` to succeed. During said time, Governance could veto the intention forever.
2. Only allow `ensureAlias` on mainnet, and check the owner of the contract at `rollupContractAddress`.

Alternative 1 was discarded because it would introduce unnecessary load on the governance process. While alternative 2 only protects networks settling on mainnet, it was preferred due to its simplicity.

## Backwards Compatibility

No backwards incompatibilities are introduced by this AZIP.

## Test Cases

The two reference chains used throughout the [Examples](#examples) section define the inputs:

- **Alpha**: `evmChainId = 1`, `rollupContractAddress = 0xAe2001f7e21d5EcABf6234E9FDd1E76F50F74962`
- **Testnet**: `evmChainId = 11155111`, `rollupContractAddress = 0xf6D0D42aCE06829bECB78C74F49879528fC632c1`

Reference Aztec address: `0x9203544e42ba86847ca8458432f7c0265ce567e74064cb25b2a9723c390463c2`.

### Deterministic chain ID

`base58btc(keccak256(abi.encodePacked(evmChainId, rollupContractAddress))[:23])`, left-padded with `'1'` to 32 characters:

| chain | text chain ID |
| --- | --- |
| Alpha | `2LKN5QVpKjqRxc2KsPM4nMojhvryewCs` |
| Testnet | `1DQUdRx75WPNrWmkcyVEyeuu9FQ6tT7x` |

### CAIP-350 binary chain ID

`keccak256(abi.encodePacked(evmChainId, rollupContractAddress))[:23]` (23 bytes):

| chain | binary (hex) |
| --- | --- |
| Alpha | `0x408a686a7c669d6a207f1b41924bedfb3f8c71b03bfc70` |
| Testnet | `0x0a5adfb53f708dedbb3450948d0160b216747667f08b63` |

### CAIP-10 mixed-case checksum

Computed against `binary_chain_hash` (see the [CAIP-2 section](#caip-2)):

| chain | checksummed address |
| --- | --- |
| Alpha | `9203544e42ba86847CA8458432F7C0265CE567e74064cB25B2a9723C390463C2` |
| Testnet | `9203544e42bA86847Ca8458432F7c0265cE567E74064cb25B2a9723C390463c2` |

A reference implementation generating these vectors is in [`../assets/azip-15/checksum.py`](../assets/azip-15/checksum.py).

## Security Considerations

### Hash security

Attackers can mine chain IDs by trying out different salts for the `CREATE2` opcode, until one of these lands a malicious contract at an address that results in the same chain ID as another one. Since lookup relies necessarily on the chain registry by definition, the attacker only has time between chain ID publication and the first call to `storeChainDetails` (which may even be done *before* chain ID publication). As long as anyone performs the call in a timely manner, the scheme is secure regardless of the hash length: a successful attack requires winning a race against any honest caller, not breaking the hash.

In particular, the 32-character base58btc-encoded hash used here carries 184 bits of entropy.

### Governance chain renaming

The `ensureAlias` function forbids Governance from attributing ill-purposed alias to any Aztec chain on Ethereum mainnet. Aztec chains settling on other EVM chains are not protected this way, but may be protected via a governance proposal itself. The worst case scenario is an ill-purposed alias being assigned to an Aztec chain.

The `setAlias` constrains the provided text chain ID to either be trivially differentiable from the deterministic hash, or be exactly that of the hash, in order to prevent governance from aliasing a chain ID to another deterministically derived chain ID.

### Changing the default Aztec chain

Changing the `aztec.on.eth` subdomain silently either breaks all previously shared interop names or makes some previously shared interop names point at unusable Aztec addresses. Governance should wait for maturity before setting this value to a chain.

### Unchecked code in the registry

No check is proposed for the code residing in the provided `rollupContractAddress` when calling any of the modifying methods of the chain registry.

Externally calling a method on an arbitrary address, counting on a specific behaviour, opens room for:
- Reentrancy
- Grievance
- Unexpected reverts
- Silent failures
- Loss of funds

It's up to the relying party to check that the address referred to by the chain ID corresponds to a valid rollup contract.

Similarly, `storeChainDetails` does not verify that any contract is deployed at `rollupContractAddress`. Registered entries are claims about a deterministic chain ID derivation, not guarantees that the chain exists; consumers MUST resolve the actual rollup contract via standard means before relying on it.

## Copyright Waiver

Copyright and related rights waived via [CC0](/LICENSE).
