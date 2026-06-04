# AZIP-10: New message-signing and fallback public keys

## Preamble

| `azip` | `title` | `description` | `author` | `discussions-to` | `status` | `category` | `created` | `requires` |
|-----|-|-|-|-|-|-|-|-|
| 10 | New message-signing and fallback public keys | Adds dedicated message-signing and fallback master public keys to the Aztec address preimage | Ilyas Ridhuan (@IlyasRidhuan), Mike Connor @iAmMichaelConnor, Nico Venturo @nventuro, Ciara Nightingale @ciaranightingale | https://github.com/AztecProtocol/governance/pull/22 | Accepted | Core | 2026-04-29 | AZIP-8 |


## Abstract

Introduces two additional public keys to bake into an Aztec address:

- Message Signing Public Key (`mspk`)
    - For signing messages in cases where authwit calls are not desirable. This key MUST NOT be used for tx authorization: that's what account abstraction is for.
- Fallback Public Key (`fbpk`)
    - For authorization in cases where the conventional path (of embracing account abstraction and performing abstract auth verification inside a smart contract) isn't acceptable.


## Impacted Stakeholders

### App Developers
This is a breaking change for two reasons: primarily, address derivation changes (`public_keys_hash` is now computed over six keys rather than four, so every account's address changes); and secondarily, the `get_public_keys_and_partial_address` oracle call now returns 8 fields instead of 6. The AZIP must therefore ship as part of a new Aztec rollup version, so as not to break existing addresses and private functions on the current rollup version. Before deploying apps on the new version, smart contract devs should recompile their contracts using the latest Aztec tooling.

### Wallets
Wallet authors MUST produce values for `mspk_m_hash` and `fbpk_m_hash` when constructing a new account, because both participate in address derivation. This AZIP does not enshrine a canonical derivation of the master secret keys `mssk_m` / `fbsk_m` from a wallet's seed, so wallets MAY either (a) stamp the canonical default hashes defined in this specification, or (b) implement their own derivation. Wallets that adopt (b) MUST use a deterministic derivation so the same seed reproduces the same address.

### Infrastructure Providers (Indexers, P2P Nodes, Block Explorers)
The `ContractInstancePublished` private-log payload grows from 13 to 15 fields, with `mspk_m_hash` and `fbpk_m_hash` inserted between `tpk_m_hash` and `deployer`. The event `version` field SHALL remain `2`. `CONTRACT_INSTANCE_LENGTH` becomes 12 (was 10). Decoders that reference fields positionally MUST update their offsets; decoders that reference fields by name MUST add the two new fields.

### Provers and Sequencers
Address derivation now hashes six single-key digests (was four) under `DOM_SEP__PUBLIC_KEYS_HASH`. The inner Poseidon2 grows from two permutation rounds to three. This affects the protocol kernel circuits that re-derive contract addresses and the AVM `address_derivation` and `contract_instance_retrieval` subtraces.

### Existing Users
This proposal is not backwards compatible: addresses derived prior to its adoption cannot be reproduced under the new derivation. Any user who wishes to carry state forward MUST migrate to a new address on the new rollup version.


## Motivation

Aztec accounts currently commit to four master public keys — `npk`, `ivpk`, `ovpk`, `tpk` — none of which are appropriate for two use-cases that the protocol does not yet serve:

1. **Signing arbitrary messages.** Apps frequently need a counterparty to attest to something — e.g. acknowledging a shared secret during a handshake — where the signer's intent is _not_ the authorization of a state-changing transaction. The existing on-chain authorization mechanism (authwits, via the account contract) is heavyweight for this purpose: it requires an extra kernel iteration, and verifying a signature via authwit leaks fragments of the signer's account-contract preimage (notably the `class_id`) to the verifier. No existing protocol key is intended to be used for direct message-signing: `ivpk` and `ovpk` are for note encryption and decryption, `npk` is for nullifier creation, and the `tpk` is intended for efficiently identifying pertinent logs in brute-force log scanning use cases.

2. **Cross-rollup migration and fallback authorization.** While Aztec remains in its Alpha phase, a critical bug in the kernel circuits, the proving system, or a popular account-contract pattern could invalidate authwits as a means of proving "I am Bob." A user in this position has no protocol-recognised path through which to demonstrate ownership of an old address to a new rollup, to an L1 portal, or to an app's recovery flow.

This AZIP introduces two new keys — committed by hash into the address preimage — to serve these two use-cases:

- The **message-signing public key (`mspk`)**, intended for non-state-changing message signatures. The corresponding secret key is expected to be used frequently and is exposed to counterparty devices that need to verify signatures from the signer. This AZIP requires that `mspk` MUST NOT be used to authorize state-changing transactions; authwits (via the account contract) remain the canonical mechanism for that.

- The **fallback public key (`fbpk`)**, intended for rare, high-stakes use: proving ownership of an old account to a new rollup, an L1 portal, or any recovery flow that cannot trust the account contract's bytecode. The corresponding secret key is expected to live in cold storage and to be touched only in those rare cases.

The two keys are introduced together rather than as a single new key, because their threat models differ in both the frequency of secret-key access and the consequences of secret-key compromise. The Rationale section discusses this trade-off in detail.

Enshrining these slots in the address preimage (rather than relegating them to an off-chain or on-chain registry) means every account commits to them at creation time, every app can read them without trusting a third-party registry, and the relationship between an address and these keys is verifiable within a single kernel iteration. The Rationale section evaluates the alternatives that were considered.

## Specification

> The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119 and RFC 8174.

### `PublicKeys` Struct

The protocol-circuits `PublicKeys` struct SHALL be extended with two additional hash slots, appended after `tpk_m_hash`:

```noir
pub struct PublicKeys {
    pub npk_m_hash:  Field,
    pub ivpk_m:      IvpkM,
    pub ovpk_m_hash: Field,
    pub tpk_m_hash:  Field,
    pub mspk_m_hash: Field, // NEW
    pub fbpk_m_hash: Field, // NEW
}
```

Each of `mspk_m_hash` and `fbpk_m_hash` SHALL be the single-key digest `hash_public_key(Point { x, y })` of the corresponding master point under `DOM_SEP__SINGLE_PUBLIC_KEY_HASH`, consistent with the hash-only treatment defined in [AZIP-8](./azip-8.md). The underlying master points (`mspk_m` and `fbpk_m`) MUST NOT be exposed to an app circuit.

`PUBLIC_KEYS_LENGTH` SHALL become `7` (was `5`).

### Address Derivation

The `public_keys_hash` SHALL be computed over six single-key digests (was four):

```
public_keys_hash = Poseidon2(
    DOM_SEP__PUBLIC_KEYS_HASH,
    npk_m_hash,
    ivpk_m_hash,
    ovpk_m_hash,
    tpk_m_hash,
    mspk_m_hash,
    fbpk_m_hash
)
```

The resulting `public_keys_hash` SHALL feed into the existing `preaddress = Poseidon2(DOM_SEP__CONTRACT_ADDRESS_V2, public_keys_hash, partial_address)` and `address = (preaddress * G + ivpk_m).x` steps unchanged.

### Default Constants

Because this AZIP does NOT enshrine a canonical derivation of the master secret keys `mssk_m` / `fbsk_m` from a wallet's seed, the protocol SHALL define default master points and their precomputed single-key hashes:

- `DEFAULT_MSPK_M_X`, `DEFAULT_MSPK_M_Y`, `DEFAULT_MSPK_M_HASH`
- `DEFAULT_FBPK_M_X`, `DEFAULT_FBPK_M_Y`, `DEFAULT_FBPK_M_HASH`

#### Derivation of the default points

Each default master point SHALL be obtained by hash-to-curve of an ASCII byte string onto Grumpkin G1, using the `affine_element::hash_to_curve(seed, 0)` recipe applied to the existing `npk` / `ivpk` / `ovpk` / `tpk` defaults. The byte-string seeds SHALL be:

| Key    | Byte-string seed |
|--------|------------------|
| `mspk` | `"az_null_mspk"` |
| `fbpk` | `"az_null_fbpk"` |

#### Derivation of the default hashes

Each default hash SHALL be `hash_public_key(Point { x: DEFAULT_*_M_X, y: DEFAULT_*_M_Y })`, i.e. `Poseidon2(DOM_SEP__SINGLE_PUBLIC_KEY_HASH, x, y)`. A protocol-circuits self-test SHALL assert consistency between each precomputed `DEFAULT_*_M_HASH` and the hash of its corresponding `DEFAULT_*_M_X` / `DEFAULT_*_M_Y` so that drift between the two is caught at build time.

#### Values

New defaults introduced by this AZIP:

| Constant              | Value |
|-----------------------|-------|
| `DEFAULT_MSPK_M_X`    | `0x00d52691f35698f962ea20f2bd0ab906c82228a434593dd28f36a3807f3043b8` |
| `DEFAULT_MSPK_M_Y`    | `0x0e27412388283d55cffb96143b2b4493b5bf6895fdb5787dadd8b0105d7531c5` |
| `DEFAULT_MSPK_M_HASH` | `0x14a5d4bde495b8c3a9ba4aed0d4870526e46fdff22d341a2f689ac5a50d10356` |
| `DEFAULT_FBPK_M_X`    | `0x1995b7952c9a39667e5333cb48435aade5e08ae1dcb066db87402e1dae09698a` |
| `DEFAULT_FBPK_M_Y`    | `0x1a07e89069fc04690e335ed68ca3914b9efd141014f24534276383c6361b1553` |
| `DEFAULT_FBPK_M_HASH` | `0x0f124f07811eebfaaa6d31316a2cc5bf255fa118f720e8ff1f2fc0d4aa46d496` |

Pre-existing defaults, unchanged by this AZIP and reproduced here so the full address-derivation input is in one place. `ivpk_m` has no precomputed `*_HASH` because its hash is computed in-circuit from `(x, y)` at address-derivation time.

| Constant              | Value |
|-----------------------|-------|
| `DEFAULT_NPK_M_X`     | `0x01498945581e0eb9f8427ad6021184c700ef091d570892c437d12c7d90364bbd` |
| `DEFAULT_NPK_M_Y`     | `0x170ae506787c5c43d6ca9255d571c10fa9ffa9d141666e290c347c5c9ab7e344` |
| `DEFAULT_NPK_M_HASH`  | `0x14fbaeaeddaa69be81d404c684e78e9f1a786d225faf8de2ce97c92f67d89a26` |
| `DEFAULT_IVPK_M_X`    | `0x00c044b05b6ca83b9c2dbae79cc1135155956a64e136819136e9947fe5e5866c` |
| `DEFAULT_IVPK_M_Y`    | `0x1c1f0ca244c7cd46b682552bff8ae77dea40b966a71de076ec3b7678f2bdb151` |
| `DEFAULT_OVPK_M_X`    | `0x1b00316144359e9a3ec8e49c1cdb7eeb0cedd190dfd9dc90eea5115aa779e287` |
| `DEFAULT_OVPK_M_Y`    | `0x080ffc74d7a8b0bccb88ac11f45874172f3847eb8b92654aaa58a3d2b8dc7833` |
| `DEFAULT_OVPK_M_HASH` | `0x0e60ed663a4da5636e2e25a1f1f0c5b27c011c8eaed22bbe61e2a0fd875dd24b` |
| `DEFAULT_TPK_M_X`     | `0x019c111f36ad3fc1d9b7a7a14344314d2864b94f030594cd67f753ef774a1efb` |
| `DEFAULT_TPK_M_Y`     | `0x2039907fe37f08d10739255141bb066c506a12f7d1e8dfec21abc58494705b6f` |
| `DEFAULT_TPK_M_HASH`  | `0x082c6d164b0ba073c9dd911100248c8ecd80b03f82f38531856a3c16dadcbef0` |

Wallets MAY stamp the default hashes into a new account's `PublicKeys` or MAY implement their own deterministic derivation. In either case the resulting hashes participate in address derivation.

### Oracle Interface

The oracle that returns public keys and partial address to a private function SHALL return 8 fields (was 6):

```
[ npk_m_hash,
  ivpk_m.x, ivpk_m.y,
  ovpk_m_hash,
  tpk_m_hash,
  mspk_m_hash,
  fbpk_m_hash,
  partial_address ]
```

An empty (`None`) oracle response SHALL pad to 8 zero fields.

### `ContractInstancePublished` Event

The `ContractInstancePublished` private-log payload SHALL be 15 fields (was 13), with `mspk_m_hash` and `fbpk_m_hash` inserted between `tpk_m_hash` and `deployer`:

```
[ MAGIC, address, version, salt, class_id, init_hash,
  immutables_hash,
  npk_m_hash,
  ivpk_m.x, ivpk_m.y,
  ovpk_m_hash,
  tpk_m_hash,
  mspk_m_hash,   // NEW
  fbpk_m_hash,   // NEW
  deployer ]
```

The event `version` field SHALL remain `2`. `CONTRACT_INSTANCE_LENGTH` SHALL become `12` (was `10`).

### Kernel Circuits

Kernel circuits that validate the contract address of a function call SHALL re-derive `public_keys_hash` over the six single-key digests as specified above. The inputs to `public_keys_hash` grow accordingly; the output remains a single field.

### AVM

The AVM `address_derivation` subtrace SHALL commit to `mspk_m_hash` and `fbpk_m_hash` and SHALL constrain `public_keys_hash` over the new Poseidon2 layout (a domain separator and six single-key digests, requiring three permutation rounds). The AVM `contract_instance_retrieval` subtrace SHALL surface `mspk_m_hash` and `fbpk_m_hash` from contract-instance preimages.

### On-Curve and Non-Infinity Validation

As per [AZIP-8](./azip-8.md), only the point-form key, `ivpk_m`, SHALL be validated on-curve and non-infinity in-circuit at the registry boundary. `mspk_m_hash` and `fbpk_m_hash` (like `npk_m_hash`, `ovpk_m_hash`, and `tpk_m_hash`) are exposed only as hashes and so cannot be validated at registration time; the registry has no way to confirm that the underlying `(x, y)` lies on Grumpkin.

Because `mspk` and `fbpk` are expected to be used in EC operations (signature verification, key validation requests), the trust burden therefore shifts to the *point of use*:

- Any app circuit (or stdlib helper) that recovers a `mspk_m` or `fbpk_m` point from its hash MUST validate the recovered point is on the curve and not infinity before performing any EC operation on it.

### Out of Scope

This AZIP does NOT enshrine any canonical derivation of the master secret keys `mssk_m` / `fbsk_m`; a wallet may choose.

## Rationale

### Why are _both_ a mspk and fbpk being proposed?

Why can't _one_ new pk be introduced instead of the two being proposed? It's helpful to look at the consequences of what can happen if the corresponding secret key is lost or stolen.

| Key | Example use case | Consequence if lost | Consequence if stolen | When is the secret key needed? | Who sees the master public key? |
|---|---|---|---|---|---|
| Message-signing secret key | A recipient signing to acknowledge a shared secret | The recipient can't handshake with new senders. | New senders can be handshaked-with, without the recipient's knowledge. New state created by those senders would not be discoverable by the recipient.  | Regularly | All counterparty devices which need to execute a tx which verifies a signature. (Even if the Mspk is app-siloed, the counterparty's kernel circuits would need to see it as part of a key validation request). |
| Fallback secret key | Demonstrating ownership of an old rollup address to a new rollup, or to an L1 portal (in cases where the old account contract's logic might have been compromised by a bug). | The user might not be able to migrate or turnstile state. | The attacker might be able to steal the user's state from the old rollup, or impersonate the user on a new rollup. | Only if migrating/turnstiling state from an old rollup (if apps make use of this key for that purpose) | Possibly only the Fbsk owner's own device, when executing kernel circuits. |

Since the fallback secret key is intended as a rare replacement of a user's abstract tx authorization mechanism (account abstraction) -- i.e. for fallback authorization of _state-changing_ transactions, the consequences of loss or theft are more severe. In the case of theft, state could be mutated, meaning funds could be stolen. In the case of loss, state could become bricked. Having a dedicated fallback secret key means it can be stored in cold storage and rarely touched.
Conversely, a message-signing secret key would be expected to be accessed and used for message signing frequently. Also, since this proposal stresses the mssk should _not_ be used for state-changing authorization, the consequences of its loss or theft ought to be less severe.

The final column ("who sees the master public key") relates to harvest-now-decrypt-later exposure against a future quantum adversary; see the Security Considerations section.

### Message-signing pk

#### Suggested usage

The master message-signing pk MUST NOT be passed into any app circuit code. This implies that the master message-signing _secret_ key MUST NOT be used directly to sign any messages; instead an app-siloed message-signing secret key MUST be used.

An app-siloed message-signing pk can be verified to relate to an address via a Key Validation Request. A hash of the master message-signing pk MAY be exposed to app circuits for this purpose, as per [AZIP-8](./azip-8.md).

This approach somewhat mitigates against "harvest-now" attacks, but not completely. A counterparty whose app circuit verifies an app-siloed-mspk-signed message must still see the master mspk, because the subsequent kernel circuit that they execute will demand the master mspk as part of processing the key validation request. So the master mspk does leak, but only to the specific counterparties a user provides signatures to, and not to any app contract nor any other observer of the user's address.

#### Alternatives Considered

##### Authwits

Aztec has "Account Abstraction", which means there are no protocol-specified keys to be used for authorizing any state-changing transactions. Instead, users can write so-called "Account Contracts" which contain custom logic for tx authorization.

> Here's an example. Sometimes, an app function might wish to check with the owner of some state variable whether the owner has given permission to mutate the variable. E.g. a `transfer_from` function of a token contract: since the `msg_sender` is not necessarily the _owner_ of the balance being decremented, the token contract seeks permission from the owner. Given the nature of "account abstraction", there is no canonical scheme for conveying "I give permission" or "I am authorising this action"; instead the user's account contract must be called because the account contract can contain any abstract notion of "I am authorising this action". Hence, the `transfer_from` function can't contain inlined logic for authorisation; it must make a call to the owner's account contract and receive a `true` response.

An authwit call could in theory be used for verifying signatures over arbitrary messages. **So why are we proposing to introduce a new Message-signing public key if authwits could be used instead?** 

- Privacy: In order for someone else to execute a tx which contains an authwit call, they would need access to more details of the signer's address preimage: acir of the authwit verification function, private function sibling path, class_id, init_hash, hashes of pks. This proposal (of instead verifying a signature from a dedicated message-signing pk) would only leak the Mspk, hashes of other pks, and the so-called partial_address. Leakage of the contract's class_id is probably the largest leakage. It's open for debate how much could practically be gleaned from such leakage because it would depend on the account contract. Leakages might include: association of the account with a particular wallet (and the wallet itself might be leaky in the way it interacts with websites or submits txs or queries data from nodes, or in its preference of `fee_payer`, or in how it chooses gas settings).
    - You could argue these leakage concerns are a problem with the chosen wallet and account contract, rather than a problem with the usage of authwits and the resulting leakage of a class_id.
- Less data to share: the signer can just share their AddressPoint instead of their address preimage details.
    - This is a somewhat weak argument by itself, since it's not much extra data.
- Proving Efficiency: It's more efficient for an app to inline-verify a standardised grumpkin schnorr signature than to make an authwit call to a recipient's account contract, which would require an extra kernel iteration.
    - This is a somewhat weak argument: authwits should be embraced, wherever possible, for consistency across apps, wallets, and users.
- Counterparty integration burden: an authwit call might require the verifier's execution environment to be familiar with the specifics of the signer's account contract -- custom capsules and other simulation-time setup that the account contract author has chosen to rely on. (Preferably, this would not be the case, and authwit standards should seek to standardise any capsules or simulation setup). A signature verified against an enshrined `mspk_m` is a self-contained primitive that any environment can verify without knowing anything about the signer's account-contract internals. Signature verification is also a relatively lightweight action compared with running an authwit.

##### Inlined Authwit verification

Instead of making an authwit call (extra kernel iteration), and revealing contract preimage data to the signature-verifying counterparty (the person who would execute the tx which verifies the authwit), perhaps the signer could provide an UltraHonk _proof_ of authwit to the signature-verifying counterparty. At the time of writing, this would cost ~11k gates to verify within a smart contract function, apparently.

The UltraHonk proof would need to be recursive: an "inner circuit" would verify the authwit and then an "outer circuit" would need to verify that the "inner circuit" actually exists inside the user's address preimage. I.e. the outer circuit would contain logic that currently exists solely in the kernels: verification of acir inside a contract address.

This might become the preferred pattern in future, but for now some tooling is missing: notably, the ability to store vanilla UH circuit acir inside an Aztec address in a way that is efficient to read within a circuit, and a reference implementation of the design.  


### Fallback pk

#### Migrations

[This forum comment](https://forum.aztec.network/t/request-for-grant-proposals-application-state-migration/8298/2) discusses the usefulness of an enshrined key -- instead of authwits -- in the case of state migrations.

Several teams are intending to abuse the tagging keypair for this purpose.

From the forum comment:

> Why does Bob need another public key to prove who he is to the next rollup instance?
> 
> Well, Aztec has account abstraction, which technically means there's no enshrined public key to represent Bob. Bob is represented by his account contract, which means the way Bob would prove "I am Bob" to a particular rollup instance is not "Here is a signature over some _canonical_ public key", but instead "A function of my account contract has successfully executed". The network doesn't care about the internals of that function: the function might actually validate a signature against some public key, but the network doesn't see that; it only recognises the successful execution of a function of Bob's account contract as evidence of "I am Bob".
>
> So if Bob wants to migrate his state from one ("old") rollup to another ("new") rollup, why can't he provide a proof of execution of a function of his old account contract to functions of the new rollup? Well, whether that is a safe approach would depend on _why_ a new rollup is being created. It's possible that the _reason_ for a new rollup is due to a bug in the old rollup (because the network is in its Alpha phase). If there's a bug in the proving system, for example, then Bob's old account contract might contain a bug. In that case, the new rollup should not trust proofs from Bob's old account contract. In that case, Bob's mechanism for proving "I am Bob" -- of furnishing a proof of successful execution of a function of his account contract -- is broken. App developers who wish to design ways for users to migrate state between rollups should account for this possibility.
>
> Hence, a new fallback public key -- which cannot be corrupted by any bugs in the Alpha phase of Aztec -- is an attractive mechanism through which Bob could prove to functions of the new rollup "I was Bob on the old rollup, so please let me migrate Bob's state over to this new rollup. I have generated a new address to be the owner of that state on this new rollup".

#### Alternatives considered

##### Use the Message-signing pk instead of an extra Fallback pk.

See "Why are _both_ a mspk and fbpk being proposed?" above.

##### Abuse the Tagging pk

Some teams were intending to use the tagging pk for migrating state between rollups. The tagging secret key has a different threat model, most notably that it is intended that the tagging secret key be kept in "hot" storage and used within the PXE. A separate fallback secret key can be separated from the PXE's "hot" secret keys and stored in cold storage.

##### Use a keypair which is completely unrelated from an address

Some teams are intending to have a separate registry which stores public keys against user addresses. In this case, the registry conveys the link between addresses and "fallback" keys, instead of enshrining the link inside an aztec address.
Some teams are using a trusted offchain registry rather than an onchain registry, which won't be an acceptable trust model in some cases, in case the db can be corrupted. In cases where an onchain registry is needed, users would have to perform an extra step of _registering_ with the registry, and they also might need to register with multiple registries for each app they use. A commonly recognised fallback public key, baked into the address preimage, provides a "registry" for free, which all apps and wallets can recognise, which can be read-from in far fewer constraints than a registry stored in state trees.

##### Use authwits

The Aztec network is still in "Alpha". In the case of a critical proving system / kernel / account contract bug, authwits could become an unreliable way to demonstrate ownership of an address, because the bytecode within that address might be corrupted: an attacker might be able to exploit a bug that returns `true` from authwit verification. The much simpler Fallback keypair would not be vulnerable to such exploits, so can serve as a reliable "fallback" in cases where account contracts can no longer be trusted, but where a user needs to demonstrate ownership of an address.



## Backwards Compatibility

This proposal is NOT backward compatible and represents a breaking change to the protocol. This AZIP MUST therefore be shipped as part of a new Aztec rollup version.

### Address divergence

Every account's address changes under this AZIP. Wallets cannot carry an existing account's address forward to a new Aztec rollup version.

### Migration

`fbpk` is the protocol's intended primitive for proving "I was Bob on the old rollup" to a new rollup, an L1 portal, or an app's recovery flow. There is, however, a bootstrap limitation worth calling out: **`fbpk` can only be used to migrate from a rollup that already includes this AZIP to its successor, i.e. from `v5` (the rollup version that introduces `mspk` / `fbpk`) to `v6` or later.** Accounts that predate this AZIP do not commit to an `fbpk_m_hash` in their address preimage, so there is nothing on the old rollup for the new rollup to verify a fallback signature against. Migrations from `v4` to `v5` must therefore use whatever non-fallback mechanisms wallets and apps already support (authwits, snapshot-based reissuance, app-specific recovery flows). Users who wish to benefit from `fbpk`-based fallback in the future SHOULD create a fresh `v5` account at migration time.

### `ContractInstancePublished` event

The `ContractInstancePublished` payload grows by two fields, but the event `version` field SHALL remain `2` because the magic value, the `version` slot itself, and the position of every existing field through `tpk_m_hash` are unchanged. Decoders that index by name and tolerate a longer payload will continue to function for the fields they already read; decoders that index positionally past `tpk_m_hash` (i.e. into `deployer`) MUST be updated.

## Security Considerations

### Invalid-curve forgery against `mspk` / `fbpk` consumers

Because `mspk_m_hash` and `fbpk_m_hash` are committed only as Poseidon2 digests of `(x, y)`, the protocol cannot enforce at registration time that the underlying `(x, y)` is actually on the Grumpkin curve. (A separate AZIP could technically modify the ContractInstanceRegistry to validate the underlying public keys within a private function before calling the existing public function of the registry, but such a feature does not exist in the protocol today. Furthermore, there are many addresses which will never register themselves with the registry, so invalid keys of those addresses wouldn't be caught by any changes to the registry). A malicious account-holder can therefore register an address whose `mspk_m_hash` (or `fbpk_m_hash`) corresponds to an off-curve point. Any app circuit that subsequently recovers `(x, y)` via a Key Validation Request, verifies the hash, and feeds the point into Grumpkin EC operations without first checking on-curve, is exposed to an *invalid-curve attack*: the off-curve `(x, y)` lies on an alternate curve `y² = x³ + b'` which may have small subgroups, and Schnorr/ECDSA-style signature verification against such a point can be forged without knowledge of any secret. The Specification therefore REQUIRES on-curve and non-infinity validation at the point of use (see "On-Curve and Non-Infinity Validation").

### Harvest-now-decrypt-later exposure of `mspk_m`

In normal use, every counterparty device that needs to verify a signature from an account's `mspk` must see the master `mspk_m` point (or, if the app-siloed pattern is used, see `mspk_m`'s digest as part of a Key Validation Request). [AZIP-8](./azip-8.md) committed only hashes of these keys precisely to mitigate harvest-now-decrypt-later attacks against a hypothetical future quantum adversary; this AZIP partially undoes that mitigation for `mspk` because the use case requires the master point to be visible at signature-verification time. App authors and wallet authors SHOULD favour app-siloed message-signing keys (verified against `mspk_m_hash` via a KVR) over the master `mspk_m` directly. `fbpk_m` does not have this problem: the `fbsk` owner's device is the only place `fbpk_m` ever needs to be reconstructed.

### Cold-storage assumption for `fbsk_m`

The threat model that justifies a dedicated fallback key (rather than reusing `mspk` or `tpk`) assumes that `fbsk_m` is held in cold storage and used only for the rare recovery / migration cases described in the Motivation and Rationale. Wallets SHOULD NOT prompt for `fbsk_m` during normal operation, and apps SHOULD NOT design flows that require `fbsk_m` frequently. A wallet that quietly uses `fbsk_m` for routine signing collapses the threat model into the same surface as `mspk` and erodes the case for two keys.

### `mspk` MUST NOT be used to authorize state-changing transactions

The Specification requires that `mspk` is not used for transaction authorization (that is the role of account abstraction / authwits). This requirement is normative for app authors but cannot be enforced at the protocol layer.

## Copyright Waiver:
Copyright and related rights waived via [CC0](https://github.com/AztecProtocol/governance/blob/main/LICENSE).
