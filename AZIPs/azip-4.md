# Aztec Improvement Proposal: L1 Block Header Access via an L1 Portal

> *This proposal is an out-of-protocol alternative to the in-protocol "L1 Block Header Access" design proposed in [PR #24](https://github.com/AztecProtocol/governance/pull/24). It reaches roughly the same capability — letting Noir contracts read and prove Ethereum L1 state — with no changes to the protocol circuits, the AVM, the kernels, or any deployed application ABI, at the cost of higher per-read gas and higher L1→L2 latency. The original out-of-protocol design is credited to Michael Connor (@iAmMichaelConnor) and was seeded as a [comment](https://github.com/AztecProtocol/governance/discussions/12#discussioncomment-16852909) by Joe Andrews on the AZIP-4 discussion. Where this document refers to "the in-protocol design," it means the design in PR #24.*

## Preamble

| `azip` | `title`                          | `description`                                                                                                       | `author`                                                                                                  | `discussions-to`                                           | `status` | `category` | `created`  |
| ------ | -------------------------------- | ------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- | -------- | ---------- | ---------- |
| 4      | L1 Block Header Access via an L1 Portal | Expose recent L1 block hashes to contracts via an L1 portal and a slashable proposer duty, with no protocol or circuit changes. | Michal Rzeszutko (@mrzeszutko), Michael Connor (@iAmMichaelConnor), Joe Andrews (@joeandrews) | https://github.com/AztecProtocol/governance/discussions/12 | Draft    | Core       | 2026-06-08 |

## Abstract

Aztec contracts cannot read Ethereum state. This AZIP makes recent L1 block hashes available to contracts without touching any critical, circuit, or AVM code.

An L1 contract — the **block-hash portal** — reads `blockhash(block.number - 1)`, packs it together with the L1 block number into a single field-sized commitment, and sends that commitment through the existing L1→L2 inbox to an L2 standard contract — the **block-hash store**. Block proposers MUST include the portal call in their checkpoint multicall; a new node-enforced slashing offense penalizes omission.

The store consumes the inbox message exactly once, verifies that the canonical RLP-encoded L1 block header (supplied as a witness) keccak-hashes to the inbox-committed hash, and memoizes a Poseidon2 commitment of the verified RLP header into public state keyed by L1 block number. Applications then **read** the header commitment — never re-consuming the message — verify their RLP-header witness against it with a cheap Poseidon2 check (~1–2k gates in place of a ~25k-gate keccak), and run Merkle-Patricia-trie, receipt, or beacon-state proofs against the extracted roots, exactly as the in-protocol design does.

The store is a "standard contract" with a deterministic per-network address (the same derivation recipe as today's `AuthRegistry` / `PublicChecks` — canonical salt, zero deployer — plus one initializer argument: the network's portal address), re-derivable by anyone from the compiled class and the portal address already carried in the rollup's L1 contract address set, and published once by a permissionless L2 transaction — **not** a magic-slot protocol contract. The design therefore introduces no kernel, protocol-circuit, or AVM changes, no recompile of deployed application circuits, and no change to the L1 `GenesisState`; a new standard contract can be added to a running rollup without a new Rollup version. The only consensus-layer change is the new slashing offense; nodes adopt it via a grace window (detection enabled, voting disarmed) before the AZUP-scheduled activation epoch arms slashing — see Backwards Compatibility. The trade-offs are higher L1 gas per checkpoint, higher AVM gas in `submit()` (one keccak + one Poseidon2 over the ~550-byte RLP header, amortized once per L1 block across all readers), and an L1→L2 readability latency bounded below by the inbox lag (~144 s expected, plus ~72 s of additional latency per consecutive missed push).

The inbox message commits *only* the L1 block number and the L1 block hash. Pre-committing additional curated header fields (e.g. `prev_randao`, `timestamp`) and switching the committed value to the beacon block root (via [EIP-4788](https://eips.ethereum.org/EIPS/eip-4788)) were both considered and rejected; see Alternatives Considered.

## Impacted Stakeholders

**Sequencers / proposers.** Proposing a checkpoint gains one new duty: include `BlockHashPortal.pushLatest()` before `propose()` in the same L1 transaction. Omission or out-of-order placement is slashable. The added L1 gas is ~10k gas in-protocol plus ~20–50k gas for the portal call per checkpoint, depending on whether the inbox tree was already touched between checkpoints. The call takes no arguments, and proposers are not responsible for consuming the message on L2.

**Application developers.** A new, opt-in capability to read and prove L1 state. Existing applications need not recompile unless they choose to adopt the new capability; readers receive the store's per-network address as configuration (re-derivable from the compiled class plus the network's portal address). Per-read header verification adds a Poseidon2 check against the memoized header commitment.

**Oracle providers, token / messaging bridges, lending markets, restaking protocols.** The same use cases the in-protocol design enumerates, served via the stored block hash: prove balances and prices against `state_root`, prove deposits and events against `receipts_root`, prove validator data against the beacon root. These are proof-backed (marginal-overhead) reads. The L1→L2 inbox remains available and authoritative for deposit notifications; this adds an independent verification path.

**Provers.** Negligible impact — no change to the proving system or to checkpoint composition.

**Node-software / slashing maintainers.** A new `OffenseType` and an accompanying watcher must be added to the slasher (see Specification (d) for detection logic). The on-chain `Slasher` / `SlashingProposer` voting and execution path is reused unchanged.

**Keepers.** Permissionless L2 actors call `submit()` after the L1→L2 message lands, supplying the referenced L1 block's RLP header and paying the one-time keccak/Poseidon2 cost. Funding a keeper improves freshness; otherwise the first app needing the block can call `submit()` itself.

**Infrastructure (RPCs, indexers, block explorers).** Two new contracts to track: the L1 portal (deployed per-network and registered in the rollup's L1 contract address set alongside `Rollup` / `Inbox`) and the L2 standard store (per-network address derived from the compiled class plus the network's portal address). There are no serialization changes to core headers or `GlobalVariables`.

## Motivation

If an Aztec contract wants to know anything about Ethereum — a balance, a price, whether a deposit landed — it must currently trust an oracle or push data through the L1→L2 inbox by hand. Both add latency, cost, and trust. Aztec is an Ethereum rollup, and a recent L1 block hash is enough to anchor a trustless proof of any L1 state, with no trust beyond L1 consensus. This is the same problem the in-protocol design in [PR #24](https://github.com/AztecProtocol/governance/pull/24) addresses.

This AZIP proposes a different way to reach that goal. Instead of adding L1-header data to protocol circuits, shared headers, and AVM interfaces, it uses the existing L1→L2 inbox plus an L2 standard-contract store. This avoids changes to critical, circuit, or AVM code and keeps deployed application ABIs unchanged.

The tradeoff is that freshness is enforced by slashing rather than by an atomic Rollup call, and readers pay a higher per-read cost unless their proof already dominates the header check. The Rationale and Security Considerations sections quantify these costs.

## Specification

> The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119 and RFC 8174.

### Glossary

| Term | Meaning |
| --- | --- |
| Block-hash portal (or "portal") | An L1 contract — deployed per-network alongside `Rollup` / `Inbox` and registered in the same `L1ContractAddresses` set — that reads `blockhash` and sends the L1→L2 message. |
| Block-hash store (or "store") | The L2 standard contract that consumes the message and memoizes a Poseidon2 header commitment into public state. |
| `blockhash(n)` | EVM opcode. Returns `keccak256(rlp(header_n))` for L1 block `n`; available only for the last 256 L1 blocks. |
| Standard contract | An L2 contract at a deterministic address derived from its compiled class, the canonical standard-contract salt (`1`), the zero deployer, and its initializer arguments (which enter the derivation via the initialization hash). Published to L2 by a permissionless `publishContractClass` + `publishInstance` transaction — **not** committed in the L1 `GenesisState`, and **not** a magic-slot protocol contract the kernel reasons about. |

### (a) Contracts

**`BlockHashPortal` (L1).** A new, non-critical L1 contract, deployed once per network using the same flow as today's `Rollup` / `Inbox` / `Outbox` / `Registry`. Its address is added to the rollup's L1 contract address set (the same `L1ContractAddresses` shape that already carries `rollupAddress`, `inboxAddress`, etc., passed to nodes via configuration); there is no cross-network canonical address. It exposes `pushLatest()`, which:

1. Reads `n = block.number - 1` and `h = blockhash(n)`.
2. Computes the content commitment (see (b)).
3. Calls `inbox.sendL2Message(recipient = BlockHashStore, content, secretHash = compute_secret_hash(0))`. The message carries no secret, so the portal commits the secret-hash of the zero secret (see (b)); `submit()` consumes it with `secret = 0`.
4. Emits `BlockHashPushed(uint256 indexed n)`. This event is the canonical signal of duty satisfaction: the slashing offense in (d) is decided by its presence and position in the proposer's L1 transaction receipt. The event intentionally omits `h`; `submit()` is authenticated by the inbox commitment, not by event data, and reconstructs `content = sha256ToField(n ‖ h)` before consuming the message.

`inbox.sendL2Message` reverts only on immutable-portal misconfiguration or out-of-gas. Both revert `propose()` rather than silently omitting the push, so (d) can be decided from the receipt of any landed checkpoint transaction.

The portal is intentionally thin: it carries no RLP decoder, no header parsing, and no L1-side application logic beyond the three steps above. Keeping it minimal preserves the design's audit-surface advantage and its Ethereum-hard-fork-format independence (see Security Considerations).

**`BlockHashStore` (L2).** A new **standard contract** — a normal contract whose address is deterministically derived from its compiled class plus the canonical salt (`1`), the zero deployer (the same recipe used by today's `AuthRegistry` / `PublicChecks`), and one initializer argument: the network's portal address (see "Portal-pair binding" below). The compiled class — the audited artifact — is identical on every network; only the instance address varies per network, and anyone can re-derive it from the class plus the portal address in the network's L1 contract address set. The contract instance itself is materialized on L2 by a one-time permissionless `publishContractClass` + `publishInstance` transaction; the L1 `GenesisState` is unchanged. It MUST NOT be a magic-slot protocol contract; see Rationale. It exposes:

```
// PUBLIC function.
submit(l1BlockNumber, l1BlockHash, rlp_header, secret = 0, leafIndex):
    if header_commitments[l1BlockNumber] != 0:
        return                                                                        // idempotent: already memoized, no-op (keeper-race-safe)
    content = sha256ToField(l1BlockNumber ‖ l1BlockHash)
    consume_l1_to_l2_message(content, secret, sender = BlockHashPortal, leafIndex)  // verifies membership, nullifies
    assert(keccak256(rlp_header) == l1BlockHash)                                     // verify the witnessed RLP matches the canonical hash
    header_commitments[l1BlockNumber] = poseidon2(pack_to_fields(rlp_header))         // memoize cheap reader-side commitment to the verified RLP
    if l1BlockNumber > latest_l1_block:
        latest_l1_block = l1BlockNumber                                               // monotone pointer to freshest memoized block
    emit_public_log(BlockHashMemoized(l1BlockNumber))                                 // SHOULD: ergonomic signal for off-chain indexers (see prose)

// PUBLIC view.
get_latest() -> (l1BlockNumber, header_commitment):
    let n = latest_l1_block
    return (n, header_commitments[n])                                                 // (0, 0) before any submit
```

`submit()` MUST be a **public** function, for two reasons: only public functions can write public state, and the public consume checks the live message-tree tip, so it can consume as soon as the message lands without assembling a historical witness. It is **permissionless** — any L2 actor MAY call it (see (f)).

`submit()` MUST verify `keccak256(rlp_header) == l1BlockHash` before writing `header_commitments[l1BlockNumber]`. The keccak is paid once per L1 block by the submitter (a keeper or first caller) in AVM gas; every subsequent reader skips it, verifying the cheap Poseidon2 commitment instead (see "Application-side verification" below). If the assertion fails, the entire `submit()` call reverts — including the inbox consume — leaving the message available for re-submission with the correct `rlp_header`.

`submit()` SHOULD emit a `BlockHashMemoized(l1BlockNumber)` public log on the success path (i.e. when memoization actually occurs), mirroring the L1 portal's `BlockHashPushed(n)` event so off-chain indexers, explorers, and keepers can detect "block `n` is now memoized" without polling public state. The log MUST NOT fire on the idempotent early-return branch, so the presence of a log carries the meaning "this call performed the memoization." The log's shape is non-normative; consumers MUST NOT couple to its field encoding. The authoritative signal that block `n` is memoized is `header_commitments[n] != 0` — the log is an off-chain notification convenience, not a substitute for the storage read.

**Portal-pair binding.** The portal pins the store as `recipient` (a constructor immutable), and the store pins the portal as the expected `sender` in `consume_l1_to_l2_message`. The store receives the portal address as its single **initializer argument**, which is what enters the L2 address derivation (via the initialization hash — Aztec's `immutables_hash` input does not carry contract values today, so the binding cannot ride on it); the same argument is also persisted in public storage for runtime reads. The mutual reference resolves at deployment time without a fixed point because an L1 CREATE address depends only on the deployer account and nonce, not on constructor arguments: the portal's L1 address is precomputed first, the store's address is derived from it, and the portal is then deployed with the store address as its immutable.

**Memoization is mandatory.** Because `consume_l1_to_l2_message` emits a nullifier, a given message is consumable exactly once. If each reader tried to consume it directly, only the first would succeed. The store therefore consumes **once**, writes the value to public state, and every subsequent reader **reads** (never consumes).

**Address recognition and activation.** The portal address is an entry in the rollup's L1 contract address set (the same configuration surface that already carries `rollupAddress`, `inboxAddress`, etc., per `L1ContractAddresses`); nodes recognize it from that configuration, not from a hardcoded constant, and it differs from network to network. The store address is deterministically derived from its compiled class plus the canonical standard-contract salt, the zero deployer, and the network's portal address as its initializer argument (initializer arguments enter Aztec address derivation through the initialization hash). The class hash is network-independent — one audited artifact serves every network — while the derived instance address is per-network. Because the only per-network input is the portal address, the store introduces no new configuration surface: clients re-derive its address from the compiled class plus the `L1ContractAddresses` entry the portal already requires, and node software SHOULD expose the derived address (e.g. via node info) for applications and tooling. The store's one-time `publishContractClass` + `publishInstance` transaction carries no special authority because clients re-derive the address rather than trusting the publisher. Re-derivation is also what defends consumers against a substituted address: a reader — including a **private** reader, which cannot read live public state and takes the store address as a witness — recomputes the expected address from the audited class hash plus the portal entry in `L1ContractAddresses` and rejects any address that does not match, so a malicious or misconfigured store address is detectable rather than silently trusted.

### (b) Content / message encoding

The inbox message `content` MUST be exactly:

```
content = sha256ToField( l1BlockNumber ‖ l1BlockHash )
```

with `l1BlockNumber` a fixed-width `u64` (big-endian) and `l1BlockHash` the 32-byte keccak block hash. No additional fields MAY be appended.

The following MUST be pinned bit-for-bit so Solidity and Noir agree:

- **Field size.** `sha256ToField` means SHA-256 followed by top-byte-drop reduction to 248 bits, ensuring the value fits in an Aztec field.
- **Witnesses.** `l1BlockHash` and `rlp_header` are supplied to `submit()`. The store recomputes `content`, verifies `keccak256(rlp_header) == l1BlockHash`, and stores `poseidon2(pack_to_fields(rlp_header))`.
- **Number binding.** `l1BlockNumber` MUST be in the preimage; otherwise a caller could store a real hash under the wrong block number.
- **Canonical serialization.** Field order, concatenation, endianness, and reduction MUST be identical in Solidity and Noir.
- **`secretHash`.** The message carries no secret. The portal MUST set `secretHash = compute_secret_hash(0)` — the Poseidon2 secret-hash of the zero secret, using the network's canonical `DOM_SEP__SECRET_HASH` domain separator — and `submit()` MUST consume with `secret = 0`. The derivation MUST be identical in Solidity and Noir.

**Reader-side binding.** The inbox authenticates `content` with `sha256ToField`. `submit()` resolves that binding once by recomputing the content and verifying `keccak256(rlp_header) == l1BlockHash`; after memoization, readers verify only `poseidon2(pack_to_fields(rlp_header)) == header_commitments[n]`.

### (c) Proposer duty and multicall

Each block proposer MUST include a `BlockHashPortal.pushLatest()` call in the same L1 transaction that submits their checkpoint, and the call MUST execute *before* `propose()` so the inbox emission appears in the receipt ahead of the `CheckpointProposed` log used as the slashing anchor (see (d)). The call MAY be:

- a direct child of Multicall3 (`0xcA11bde05977b3631167028862bE2a173976CA11`) — the canonical bundling pattern most proposers use — placed ahead of the `propose()` call in the multicall's call list; or
- a sibling of `propose()` inside a proposer-side wrapper that itself forwards into Multicall3 — notably the Spire Proposer (`0x9ccc2f3ecde026230e11a5c8799ac7524f2bb294`), which a subset of proposers run today. The wrapper MUST forward the `pushLatest()` call into the underlying Multicall3 so that, after flattening, its execution precedes `propose()`.

The push must be in the proposer's checkpoint transaction so the duty is attributable to that proposer. A `pushLatest()` call in any other L1 transaction does not satisfy the duty, even if sent by the same proposer in the same L1 block. This avoids third-party or accomplice pushes masking an omitted duty. The message is not swept into the checkpoint proposed by the same transaction: `sendL2Message` inserts into the in-progress inbox tree, so the value becomes readable only after the inbox lag.

Ordering also lands the message in the earlier in-progress tree when `propose()` crosses the `LAG` boundary, surfacing the value one checkpoint sooner; freshness is the latency rationale, but the slashing rule in (d) is what makes it enforceable.

### (d) New slashing offense

A new offense is added to the existing node-enforced slashing framework (`Slasher` / `SlashingProposer` / `OffenseType`):

- **Definition.** A proposer's L1 transaction submitting the checkpoint did not emit a `BlockHashPushed(n)` log from the configured portal address (read from the rollup's L1 contract address set) before the `CheckpointProposed(checkpointNumber, …)` log emitted by the rollup. Either a missing portal log or an out-of-order portal log (placed at or after the `CheckpointProposed` log) constitutes the offense.
- **Detection.** The watcher fetches the proposer's checkpoint-tx receipt via `eth_getTransactionReceipt` and inspects `receipt.logs`. It locates (i) the `BlockHashPushed` log emitted by the configured portal address, identified by `log.address == portalAddress` and `log.topics[0] == keccak256("BlockHashPushed(uint256)")` — taking the lowest `logIndex` if multiple appear — and (ii) the `CheckpointProposed` log emitted by the rollup, identified by `log.address == rollupAddress`, `log.topics[0] == keccak256("CheckpointProposed(uint256,bytes32,bytes32[],bytes32,bytes32)")`, and `log.topics[1] == checkpointNumber`. The offense fires if the portal log is absent, or if its `logIndex` is greater than the matching `CheckpointProposed` log's `logIndex`. The watcher does not need trace or debug RPC; `eth_getTransactionReceipt` is sufficient because reverted sub-calls in the EVM discard their logs, so the mere presence of `BlockHashPushed` from the configured portal in the receipt implies a successful inbox emission.
- **Severity.** Small. The offense degrades freshness, not safety. The slash amount matches every other small-severity offense penalty in the existing slasher (`10e18` wei, see (e)). No late-arrival tolerance window applies: the offense is decided deterministically from the proposer's finalized L1 transaction receipt, so there is nothing analogous to `SLASH_DATA_WITHHOLDING_TOLERANCE_SLOTS` to wait out. Adjudication MUST route through the existing `SlashingProposer` voting/execute path.

### (e) Block-selection rule and parameters

- The portal MUST reference `block.number - 1` (the parent of the executing L1 block). The portal recomputes the hash at execution time, so a reorg simply yields the new canonical chain's parent; the call never reverts on a reorg (see Security Considerations).
- No monotonicity check is required. Consecutive checkpoints land in strictly increasing L1 blocks; gaps are benign (the store keys by number) and a duplicate deposit for the same number carries the same hash.

| Parameter | Value |
| --- | --- |
| Referenced L1 block | `block.number - 1` |
| `secretHash` | `compute_secret_hash(0)` (consumed with `secret = 0`; never a raw `0` — see (b)) |
| Slash amount | `10e18` wei. Matches `SLASH_DATA_WITHHOLDING_PENALTY`, `SLASH_INACTIVITY_PENALTY`, and every other small-severity offense in `yarn-project/slasher/src/generated/slasher-defaults.ts`. Falls in the SMALL bucket — `AZTEC_SLASH_AMOUNT_SMALL` floor is `10e18` per `l1-contracts/generated/default.json`. |
| Detection tolerance | None. The offense is decided purely by inspection of the proposer's finalized L1 transaction (see (d) Detection); there is no late-arrival tolerance window analogous to `SLASH_DATA_WITHHOLDING_TOLERANCE_SLOTS = 3`. |

### (f) Consumption on L2

Consuming the landed message and memoizing it is a second liveness dependency, and it is not covered by slashing; slashing covers only the L1 push.

- `submit()` is **permissionless**. A keeper or first caller may call it after the message lands. Messages do not expire, so the tradeoff is freshness rather than availability: without a funded keeper, low-demand blocks may remain unmemoized until first use.
- A proposer-consume duty (folding the consume into the slashable obligation) is **rejected**. The sequencer is an L1-only actor today: it holds no L2 account, runs no client-side private proving, and pays no L2 fees. Every Aztec transaction mandatorily carries a private-kernel proof and is authenticated from a private account entrypoint, so a "just call `submit()`" transaction would be a full proven L2 user transaction, not a free self-include. Making the proposer consume would require net-new protocol-level system-transaction injection that does not exist today.

**Reader access after memoization.**

- **Discovery / latest available.** Apps that want the freshest L1 block currently memoized call `get_latest()` rather than knowing the L1 block number out-of-band. `latest_l1_block` is monotone: each `submit(n, …)` with `n > latest_l1_block` advances it, and out-of-order submissions for older blocks still populate `header_commitments[n]` but do not regress the pointer. Apps targeting a specific historical block read `header_commitments[n]` directly; a `0` return means "not memoized yet" (`l1BlockNumber = 0` is unreachable in practice because the portal references `block.number - 1` from a live Aztec chain).
- **Public readers** read `header_commitments[n]` directly from public state and verify their witnessed RLP header against it with a Poseidon2 check — cheap, no proof. Within a block, public execution is sequential: a read sees `header_commitments[n] != 0` only if it executes *after* the `submit()` that wrote it (later in the same tx, or in a later tx of the same L2 block). A public reader that lands before the keeper's `submit()` in block `K` reads `0` and MUST either wait for block `K+1` or fold its own `submit()` into the same tx (see below).
- **Same-tx composability.** An app MAY bundle `submit()` before its consumer call in the same tx. This removes keeper-race uncertainty at the cost of paying the one-time `submit()` gas.
- **Private readers** cannot read live mutable public state. They use the same mechanism the in-protocol design uses for historical access: `get_block_header_at(K)` (archive-root membership, ~3k constraints) followed by `public_storage_historical_read(header, slot, STORE_ADDR)` — a public-data-tree Merkle path against the block's deterministic public-data root. Block `K`'s header only enters the archive when block `K` is sealed, so a private read of a value `submit()` wrote in block `K` is possible only from block `K+1` onwards — there is no in-block private composition with `submit()`. A not-yet-written slot deterministically reads `0`, which apps MUST treat as "not available yet." This adds at least one L2 block (~6 s) over public readers.

**End-to-end timing.** Mapping the full path from a proposer's checkpoint at slot `N` to a successful read:

| Stage | Earliest L2 slot | Approx. wall time from `N` |
| --- | --- | --- |
| L1 push lands (portal call inside checkpoint multicall) | `N` | 0 |
| Inbox message consumable on L2 | `N + LAG` | ~144 s |
| `submit()` memoizes `header_commitments[n]` | `K ≥ N + LAG` (whenever a keeper / first caller lands) | + keeper latency |
| First public read sees the value | `K` (txs after `submit()`); or same tx via composability | same block as `submit()` |
| First private read sees the value | `K + 1` (archive must contain block `K`) | +1 L2 block (~6 s) over public |
| Each consecutive missed push (slashable) | — | +72 s before next honest proposer fills in |

### Application-side verification

Applications verify against the memoized header commitment before using roots extracted from their witnessed header:

```noir
// commitment = store.header_commitments[n]  (public read, or historical read for private callers)
assert(poseidon2(pack_to_fields(rlp_header)) == commitment);   // ~1–2k-gate check, no keccak
let roots = rlp::extract(rlp_header);                           // state_root, receipts_root, ...
mpt::verify_account(roots.state_root, account, account_proof);
// ... and storage / receipt / beacon proofs as needed.
// Apps that need the canonical 32-byte keccak block hash (e.g. matching an external `bytes32` blockhash
// identifier) derive it on demand via `keccak256(rlp_header)` after the Poseidon2 check passes (~25k gates).
```

A shared, audited aztec-nr library SHOULD wrap the RLP header check and the MPT, receipt, and beacon proofs so consumers share one verification surface.

## Rationale

### Why call the portal from the multicall, not from the Rollup contract

Putting `blockhash` + `sendL2Message` inside `propose()` would give a hard, atomic guarantee, but it would require a Rollup contract change and critical-path audit. The multicall approach keeps the Rollup untouched and expresses the requirement through slashing instead: skipped pushes degrade freshness, not safety.

### Why a standard contract, not a magic-slot protocol contract

The store is used by applications, not by the kernel. A magic-slot protocol contract would require kernel constants and protocol-circuit changes; a standard contract gives applications a deterministic, source-derivable address (re-derived per-network from the compiled class plus the network's portal address) without adding kernel surface. Portal-pair authentication works in either tier because both sides bind by derived address.

### Why a commitment and a bound block number

A commitment is required because a raw 256-bit block hash does not fit in one field. The block number is bound because the inbox message otherwise gives the store no trustless way to know which L1 block the hash belongs to. There is no domain-separation tag because `sender = BlockHashPortal` and `recipient = BlockHashStore` already segregate this message shape.

### What is committed, and why only the block hash

The inbox commits `{l1BlockNumber, l1BlockHash}`. `submit()` verifies a full RLP header against that hash and memoizes a Poseidon2 commitment to the verified header. Applications can then extract any header field from their witnessed RLP header after a ~1–2k-gate Poseidon2 check plus the relevant RLP decoding.

The tradeoff is cost rather than coverage: committing only the block hash avoids a canonical header-field list, but header-field-only reads pay per-read decoding instead of reading pre-extracted fields.

### Why `block.number - 1`

Reorgs remove a contiguous chain suffix. If the referenced block `N = B - 1` is reorged, then `B` (the block containing the multicall) is reorged too. The referenced block is therefore at least as final as the checkpoint's own L1 anchor. The portal also recomputes the hash at execution time, so a reorg changes the canonical message rather than making `propose()` revert.

### Why no monotonicity check

The store keys by L1 block number. Gaps are benign, duplicates carry the same hash, and apps that need ordering can compare block numbers themselves.

### Per-read cost analysis

The cost depends on whether the application already needs a Merkle-Patricia-trie proof:

- **Case A — proof-backed reads** (balances, storage, receipts, validator data). A real Merkle-Patricia-trie proof already runs ~8 in-circuit keccaks (one per trie level, branch nodes up to 532 bytes); the portal adds **one Poseidon2 verify** of the memoized header commitment (~1–2k gates), <5% over the MPT path. For the headline use cases (oracles, bridges, lending, restaking), this is negligible.
- **Case B — header-field-only reads** (`prev_randao`, `timestamp`). These cost one Poseidon2 verify plus a small RLP-field decode, roughly ~1–3k gates. That is materially worse than a pre-extracted field, but bounded and avoids putting an RLP decoder in the portal or store.

| Per-read header cost | In-protocol (Poseidon2 open of 6 fields) | Portal (Poseidon2 verify of memoized header + RLP extract) | Beacon-only |
| --- | --- | --- | --- |
| Gates | ~150 | ~1–3k | ~96k |
| Relative | 1× | ~7–20× | ~640× |

### Storage growth

`pushLatest()` runs once per Aztec checkpoint, so `submit()` memoizes one L1 block per checkpoint — one field-sized public-state slot (`header_commitments[n]`) every `AZTEC_SLOT_DURATION = 72 s`, i.e. ~1,200 slots/day, ~438k slots/year. Entries are never overwritten or pruned: indefinite retention is required because any future proof against block `n` verifies against `header_commitments[n]` directly, while `blockhash(n)` on L1 is only available for the last 256 blocks and cannot be reconstructed trustlessly once that window closes.

A future AZIP MAY introduce a sliding-window pruning policy (e.g. retain only blocks within the deepest archive depth applications still target). The encoding chosen here — keyed solely by L1 block number, no internal cross-references — is compatible with such a policy.

### Alternatives considered

**In-protocol commitment ([PR #24](https://github.com/AztecProtocol/governance/pull/24)).** The design this proposal offers an alternative to. Commits six L1 header fields inside the protocol and exposes them via a new AVM opcode and a ~150-gate Poseidon2 opening. Heavier protocol surface (new circuit witnesses across three rollup variants; new fields in five header/global types; critical-path `ProposeLib.sol` changes; recompile of every deployed application circuit), but cheaper per-read. Deployed circuits carry an Ethereum header-format dependency: a hard fork that alters the committed fields requires coordinated recompilation.

**Rollup-internal call.** Sending the inbox message directly from `propose()` rather than the multicall. Rejected: critical-path change requiring core-contract audit and an AZUP, and incompatible with an ownership-renounced, immutable Rollup ([AZIP-3](./azip-3.md)).

**Raw block hash as content.** Rejected because a raw 256-bit `blockhash` often exceeds `MAX_FIELD_VALUE`, and because the block number still needs to be bound into the inbox content.

**Proposer-consume duty.** Folding the L2 `submit()` consume into the slashable proposer obligation. Rejected; see Specification (f) for the reasoning.

#### Compile-time portal pinning (per-network class hash)

Considered: baking the network's portal address into the store's compiled source as a generated global, keeping a no-arg constructor exactly as in the `AuthRegistry` recipe.

Rejected because the baked-in address makes the compiled class — and with it the audited artifact, the class publication, and the contract build pipeline — per-network, while still failing to produce a cross-network address constant (the portal address differs per network, so the derived store address does too, either way). Instance-level pinning through the initializer argument confines the per-network variation to the instance address, keeps a single network-independent class, and the address remains re-derivable from configuration the proposal already requires.

#### Inbox sender rewrite (fee-asset-portal-style magic sender)

Considered: having the Inbox rewrite the portal's `sender` to a network-independent magic value at message insertion, as it does today for the fee-asset portal (where the L2 contract validates against `FEE_JUICE_ADDRESS` rather than the portal's real L1 address). This would let the store hardcode a universal sender, giving it a fully network-independent class *and* address.

Rejected because every ingredient of that pattern is a protocol privilege outside this proposal's scope: a fiat-assigned magic address baked into protocol constants, the Inbox deploying the portal in its own constructor, and a special-case branch in `sendL2Message`. The Inbox on live networks is already deployed and immutable, so adopting this pattern means a new message-bridge deployment — exactly the kind of core-contract change this proposal exists to avoid. A future AZIP MAY migrate the binding to this pattern if a new Rollup version redeploys the message bridge.

#### One-time post-deploy portal setter

Considered: publishing the store with no binding and setting the portal address once via an unauthenticated one-shot setter, decoupling the two deployments entirely.

Rejected because there is no party to authenticate the setter against — standard contracts are published by the zero deployer — so the call is front-runnable: an adversary could bind the store to a hostile portal before the legitimate setter lands, gaining the ability to memoize fabricated headers.

#### Beacon-root-only content (`parent_beacon_block_root` via EIP-4788)

Considered as a substitute for `blockhash(block.number - 1)` as the value the portal commits. The proposal would source the parent beacon block root from the [EIP-4788](https://eips.ethereum.org/EIPS/eip-4788) beacon-roots system contract at `0x000F3df6D732807Ef1319fB7B8bB8522d0Beac02` via `staticcall(abi.encode(block.timestamp))`, which returns `hash_tree_root(BeaconBlock_{S-1})` at L1 slot `S`. Applications would then reach every EL header field and the entire beacon state via SSZ Merkle proofs from that root. The L2 store and the portal-pair mechanics would be unchanged; only the committed value would differ.

Advantages of a beacon-root-only commitment:

- **Single uniform proof system.** SSZ reaches both EL state (via the `ExecutionPayload` field inside the beacon block) and beacon state (validators, balances, sync committees, slashings, withdrawals) — apps that want both pay one technology stack instead of RLP+MPT for EL and SSZ for beacon.
- **First-class beacon-chain access.** Restaking, validator-tracking, and sync-committee-driven apps walk SSZ directly from the committed root. In the chosen design, beacon access goes through the `parent_beacon_block_root` field in the L1 block header, adding a header-commitment check and one L1 slot of extra staleness for beacon data.
- **~27-hour vs ~51-minute L1 availability window.** EIP-4788's `HISTORY_BUFFER_LENGTH = 8191` slots provides ~27 hours of historical beacon roots, whereas `blockhash` is available only for the last 256 blocks (~51 minutes). Material if the permissionless L2 consume (Specification (f)) lags for any reason — under `blockhash`, the value is unreachable from L1 once 256 blocks have passed since the multicall.

Reasons for rejection:

- **EL-state access becomes more expensive per proof.** The dominant near-term demand for L1 state is EL state: bridge receipts, DeFi storage slots, and oracle balances. A beacon-root design must first prove the execution payload header through SSZ before running the same MPT proof. For these use cases, that extra SSZ path is a material regression.
- **SSZ repadding compatibility risk.** SSZ generalized indices depend on the container's padded power-of-2 size, so added fields can invalidate existing proofs against affected containers. By contrast, `blockhash == keccak256(rlp(header))` lets applications own header parsing and update their RLP/SSZ libraries without changing the portal.
#### Pre-committing additional header fields in a curated tuple

Considered: extending the content commitment to a fixed-width tuple of additional pre-extracted header fields beyond `{l1BlockNumber, l1BlockHash}` — e.g.

```
content = sha256ToField( l1BlockNumber ‖ l1BlockHash ‖ prev_randao ‖ timestamp [ ‖ … ] )
```

with the portal supplied the full RLP header, verifying `keccak256(rlp) == blockhash(n)`, and extracting the curated fields at fixed offsets. The store would then memoize each pre-extracted field to public state alongside the hash, so consumers reading `prev_randao` or `timestamp` could read them directly (a public-data-tree read, or a ~150-gate Poseidon2 open against a republished commitment) rather than paying the ~25 k-gate keccak-over-RLP tax on every read.

The win is cheaper header-field-only reads: `prev_randao` or `timestamp` could be read directly instead of being decoded from a witnessed header.

Rejected because it puts a hand-rolled RLP decoder in the L1 portal, making header offsets load-bearing for every consumer and coupling the rollup's L1 portal to Ethereum header-format changes. It also optimizes the less common header-field-only case by expanding the shared audit surface for everyone. Apps that need this at scale can deploy an application-specific portal or extractor.

#### Hash-only memoization (deferring keccak verification to every reader)

Considered: having `submit()` memoize only the 32-byte `l1BlockHash` (no `rlp_header` parameter, no header commitment), and pushing the `keccak256(rlp_header) == storedHash` check into every reader.

Soundness is identical to the chosen design: keccak preimage resistance ensures the witnessed RLP is canonical given a matching stored hash.

Rejected because it pushes a keccak over the full RLP header into every reader. That is especially poor for header-field-only reads and duplicates work across all consumers of the same block. Memoizing a Poseidon2 commitment in `submit()` lets the submitter pay the expensive hash once while keeping the store RLP-agnostic.

#### L2-side pre-extraction in `submit()`

Considered: RLP-decoding a curated set of header fields inside `submit()` and storing each as public state.

Rejected for the same reason as L1-side pre-extraction: it makes an RLP decoder part of the shared surface and couples the store to Ethereum header-format changes. It is easier to recover from than a portal bug, but still expands audit surface and adds one public state slot per pre-extracted field per L1 block. Apps that need this can build their own extractor over the verified `rlp_header`.

#### Memoizing the canonical `bytes32` block hash alongside the commitment

Considered: keeping `blockhashes[n] = l1BlockHash` alongside `header_commitments[n]`. Because a keccak digest exceeds the field modulus, it would be stored as a hi/lo field pair, lifting per-block storage from one to three field slots.

Rejected because the headline use cases (MPT/SSZ proofs from `state_root`, `receipts_root`, `parent_beacon_block_root`) consume header roots, not the block hash itself. The raw `bytes32` keccak hash is only needed by niche consumers — signatures committed to `bytes32 blockhash`, cross-chain identifiers that key by keccak, off-chain tooling reading via public-state queries. Those consumers can recover it on demand by computing `keccak256(rlp_header)` over their already-Poseidon2-verified header (~25k gates), without taxing every block's storage indefinitely. Apps with high-frequency raw-hash demand can deploy a thin caching wrapper.

## Backwards Compatibility

This proposal is net-new and opt-in. It makes no changes to existing circuit ABIs, kernels, the AVM, or core header / `GlobalVariables` serialization, so it forces no recompilation of deployed application circuits.

Three pieces require coordinated rollout:

- **Portal.** The portal contract is deployed once per network alongside `Rollup` / `Inbox` and its address is added to the rollup's L1 contract address set (`L1ContractAddresses`). Nodes consuming the slashing rule and infrastructure tracking the duty MUST read the portal address from configuration; there is no cross-network constant.
- **Slashing.** The new offense is consensus-relevant. To tolerate staggered node upgrades, it SHOULD activate after a grace window during which detection may run but slash votes are disabled, letting nodes converge before any honest proposer can be penalized. The window length and activation epoch are AZUP-scope.
- **Store.** Clients MUST derive the store address from the compiled class plus the network's portal address (the store's single initializer argument); node software SHOULD expose the derived address (e.g. via node info) so applications and tooling need not re-implement the derivation. The contract instance is published to L2 via a normal permissionless `publishContractClass` + `publishInstance` transaction. There is no cross-network address constant; readers receive the store address as configuration.

## Test Cases

The following are RECOMMENDED for the implementation:

- **Content-commitment vectors.** `(number ‖ hash) → field`, including top-byte-drop reduction, verified bit-for-bit identical between Solidity and Noir.
- **Round trip.** push → consume once → verify `keccak(rlp) == l1BlockHash` → memoize `header_commitments[n]` → public read and private historical read.
- **Invalid submit rejected.** Wrong `(number, hash)` pairs or mismatched `rlp_header` revert without consuming the inbox message or writing store state.
- **Idempotent submit.** A second `submit()` for an already-memoized L1 block number is a no-op: it does not revert, does not re-consume, and does not overwrite. This holds even when the second caller supplies a different `l1BlockHash` or `rlp_header`. Readers use the memoized value.
- **Memoization log.** `submit()` emits `BlockHashMemoized(n)` exactly on the success path. The log is absent on the idempotent early-return branch and on reverts (including the keccak-mismatch revert).
- **Latest pointer monotonicity.** Newer submissions advance `latest_l1_block`; older out-of-order submissions populate their slots without regressing it.
- **Slashing watcher — missing push.** A checkpoint transaction whose receipt contains no `BlockHashPushed` log from the configured portal address is detected as an offense. This covers both omitted-call and reverted-call cases, since the EVM discards logs of reverted frames.
- **Slashing watcher — out-of-order push.** A checkpoint transaction whose receipt contains a `BlockHashPushed` log from the configured portal but whose `logIndex` is greater than that of the matching `CheckpointProposed` log is detected as an offense.

## Security Considerations

**Reorgs.** Stored hashes are canonical-or-gone. If the multicall block `B` survives, so does its ancestor `B - 1`; if `B - 1` reorgs, `B` reorgs too and the inbox leaf disappears from canonical L1 state. Acting on unfinalized L1 state remains an application-layer risk.

**Field size and serialization.** Security depends on Solidity and Noir computing the same `sha256ToField(l1BlockNumber ‖ l1BlockHash)`. Ambiguous serialization or reduction would be a consensus bug; the 248-bit truncated SHA-256 output leaves ample collision security for this binding.

**Liveness of consumption.** The L1 push is slashable, but the L2 consume is not. Permissionless `submit()` preserves availability, while keeper funding determines freshness for low-demand blocks. Apps MUST treat a `0` read as "not available yet," never as a valid commitment.

**Latency.** The floor is `LAG × AZTEC_SLOT_DURATION = 2 × 72 s = 144 s`. Ordering `pushLatest()` before `propose()` is required by Specification (c) and enforced by the slashing rule in (d), so the post-`propose()` case does not arise for honest proposers. Keeper delay and consecutive missed pushes add to that; private readers add one L2 block.

**Freshness and monotonicity.** The store does not enforce an application-level freshness window or strict global monotonicity. Apps that need these properties MUST check the L1 block number or timestamp themselves. Safety is unaffected; stale values fail only application-level freshness requirements.

**Verified-header binding.** `header_commitments[n]` is written only after `submit()` verifies `keccak256(rlp_header) == l1BlockHash`, where `l1BlockHash` is bound by the inbox content. Readers then verify their witnessed header against `header_commitments[n]` with Poseidon2. The canonical `pack_to_fields` encoding MUST be specified bit-for-bit so AVM `submit()` and Noir readers compute the same commitment.

**Hard-fork format independence and portal audit surface.** The portal does not parse headers; it only reads `block.number`, reads `blockhash`, computes the inbox content, and calls `sendL2Message`. Ethereum header-format changes are handled by application/library RLP decoders rather than by changing the portal.

## Copyright Waiver

Copyright and related rights waived via [CC0](/LICENSE).
