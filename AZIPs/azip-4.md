# AZIP-4: L1 Block Header Access

## Cons

> *This top-of-document section focuses deliberately on cons, because they're under-explored and potentially under-appreciated relative to its benefits. Pros are discussed inline in the Motivation and Rationale sections below. This section is not part of the normative AZIP; the full proposal starts at Preamble below.*

> *Cons #1-#3 below all share a single root property of the Noir circuit model: **private circuits bake their interface assumptions into compile-time constraints, so any change to those assumptions requires recompile-and-redeploy of every circuit that touches the affected interface**. The three cons differ in what triggers the change:*
>
> | Con | Trigger | Interface affected | Failure mode |
> |---|---|---|---|
> | **#1** | Ethereum structural hard-fork (Verkle, Poseidon state commit) | L1 preimage structure | Noisy break + potential fund stranding |
> | **#2** | Ethereum semantic hard-fork (e.g. Merge's `mixHash`→`prevRandao`) | L1 preimage semantics | **Silent** wrong-data |
> | **#3** | Future Aztec AZIP revising the six-field preimage | L1 preimage | Noisy break unless apps upgrade |

**1. Ethereum structural hard-fork: potentially permanent fund stranding.** An Ethereum hard-fork that structurally changes the encoding of any committed field -- or changes the trees those fields address -- can strand user funds on every Aztec rollup version that predates the fork, *including the Aztec version that is current at the time the fork lands*, and for some app designs permanently. The six committed fields embed two implicit dependencies on today's Ethereum formats: the encoding of the fields themselves (for example, `stateRoot` being a keccak-MPT root) and the trees those roots address. An Ethereum hard-fork that changes either -- most concretely, the migration of Ethereum's state commitment to a Verkle tree, and eventually to a SNARK-friendly (e.g. Poseidon) commitment, which is on Ethereum's published roadmap -- breaks every Aztec private circuit compiled against the old format. Noir constraints are baked in at compile time and cannot adapt at runtime.

**The breakage hits the then-current Aztec version first, immediately at the fork block.** On the very next Aztec checkpoint after the L1 fork activates, the committed `l1_block_header_data_commitment` carries data in the new Ethereum format, but every deployed app has circuits expecting the old format. Every app that reads L1 state starts failing at that checkpoint. There is no grace period.

**The available recovery paths are narrower than they first appear.** Aztec's protocol circuits -- the kernels and the rollup circuits -- have **immutable verification keys by design**. The protocol does not give governance (or any other actor) the power to change what the kernels accept as a valid proof; this is a load-bearing part of Aztec's credible-neutrality story. It also means:

- *Apps outsource preimage interpretation to the kernel* -- the "L1 read requests" alternative design (see Rationale). **Under today's protocol architecture this does not actually rescue apps after an Ethereum fork**, because the kernel itself cannot be updated to understand the new format. For this alternative to work, Aztec would first need to acquire a VK-update mechanism for protocol circuits -- a major additional governance/technical change that is not on the current roadmap and that many protocol stakeholders actively oppose.

- *Aztec's L1 commitment pipeline upgrades via AZUP* -- the Solidity code in `ProposeLib.sol` (RLP extraction, SHA256 verification, freshness and monotonicity) is upgradable, so the commitment at the L1 boundary can be adapted to keep producing *some* value after a format change. But the bytes committed to Aztec still decode against the *new* Ethereum format downstream, and deployed app circuits cannot parse them. L1-side updates alone do not rescue existing apps.

- *Individual apps upgrade themselves on L2* -- an Aztec contract can deploy a new `class_id` whose circuits understand the new L1 format, and users can interact with the upgraded class. **This is the only path that actually restores L1-reading functionality under the current protocol architecture.** Three caveats, all material:
  - **Immutable apps cannot do this.** Apps that opted for immutability at deployment -- a common choice for bridges and vaults that want to reassure users about governance-free operation -- are permanently bricked for L1-reading functionality when Ethereum changes format. Users can only recover via app-level emergency exits, if those were designed in and do not themselves require L1 reads.
  - **The upgrade instigation must not itself depend on L1 reads.** A plain `class_id` upgrade is an L2 transaction and typically doesn't. But if an app's upgrade governance is gated by L1 checks (an L1-verified admin signature, an L1-based vote), the upgrade is itself blocked by the same broken L1 reads.
  - **Upgrade timing creates a downtime window.** Even when the app is upgradeable and its governance doesn't depend on L1 reads, the admin must notice the Ethereum (or Aztec) change and ship the compatible `class_id` at the right moment. Real-world reaction times are imperfect: between the fork landing and the admin deploying the new class, the still-deployed circuits expect the old L1 format but the committed data is already in the new format -- proofs revert (for structural changes) or decode silently-wrong data (for semantic changes), and users cannot reliably transact against the app. The width of this window is bounded only by how closely the admin team tracks the relevant release calendars; a misaligned upgrade can extend the downtime indefinitely.

Two distinct windows therefore produce stranding. First, **the acute window between the L1 fork and affected apps shipping compatible `class_id` upgrades**: if app developers have not pre-prepared an upgrade, every user of the affected apps loses L1-read functionality with no alternative available yet. Second, **the residual window after upgraded classes are published**: users who have not yet transacted against the upgraded class remain on the previous one until they do.

**Stranding is indefinite -- not merely delayed -- under any of the following conditions, which together cover a large fraction of plausible L1-reading app designs:**

- The app is **immutable**: its circuits cannot be replaced at all. Users can only recover funds via app-level emergency exits that don't themselves need L1 reads, if such exits exist.
- The app is upgradeable, but its **exit path depends on L1 reads**: the broken reads block any withdrawal or migration transaction, even though a new class is available.
- The app is upgradeable with an L1-read-free exit path, but its **upgrade instigation depends on L1 reads**: the upgrade itself is blocked by the same broken L1 reads.

In any of these cases, funds remain stuck until the app is repaired at the application layer (sometimes impossible) or until governance intervenes with an AZUP that directly edits the bricked app's state. This is not hypothetical: Ethereum's roadmap explicitly includes a state-trie migration to a SNARK-friendlier structure (Verkle trees first, then potentially a Poseidon-based commitment).

**2. Silent-breakage sibling of #1 (trigger: Ethereum semantic hard-fork).** Where #1 is about Ethereum changing the *structure* of the committed fields (noisy break, circuits can't decode), #2 is about Ethereum changing the *meaning* of a committed field without changing its position or encoding. At The Merge (Sept 2022), `mixHash` was silently repurposed as `prevRandao`: same slot, same bytes, same encoding, but a completely different data source (PoW mining → beacon-chain RANDAO). An application circuit reading that slot before and after the Merge decodes identical bits and produces superficially valid proofs *against a different real-world quantity*. The failure is silent rather than loud -- which is worse in practice, because nothing is flagged as broken. If Ethereum similarly repurposes any of this AZIP's six fields, circuits that read the affected field will silently produce wrong answers until apps migrate.

*This risk is not AZIP-4-specific.* Any design that exposes L1 field data to application circuits (including the L1→L2-message copier alternative) hits it equally, since apps hard-code the interpretation regardless of the delivery mechanism.

**3. Aztec-initiated sibling of #1 (trigger: future AZIP revising the preimage).** The same compile-time-constraint mechanism rules out mid-version preimage revision by Aztec itself. Adding, removing, or reordering fields in the commitment would brick every deployed private circuit that reads it; the only truly safe revision is a major Aztec version bump with empty-state migration. In practice this means: the six fields this proposal chooses are the six fields app developers get until the next major version. (A future AZIP could defer field interpretation to the kernel -- see the "L1 read requests through the kernel" alternative in Rationale -- but that design is complex and has its own governance prerequisites.)

**4. Proposer-chosen L1 blocks carry reorg risk that translates primarily into missed L2 slots and degraded network throughput.** The freshness window permits the proposer to commit an L1 block as recent as `block.number - 1` (~12 s of L1 history). Under Ethereum's probabilistic finality, very recent L1 blocks have non-negligible reorg probability; full finality arrives only after two epochs (~12.8 min). Reorg probability decays rapidly with block age.

**The primary risk is proposer liveness, not app-facing invalidation.** If the proposer builds an Aztec checkpoint committing to L1 block `N` and `N` is subsequently reorged out of the canonical chain before `propose()` lands, the `propose()` transaction fails at step 1 (`keccak256(rlpL1BlockHeader) != blockhash(l1BlockNumber)`) -- the proposer wastes their slot, no checkpoint lands, and no L2 blocks in that checkpoint are produced. Aggregated over the network, a proposer population that consistently picks the freshest permissible L1 block converts ambient L1 reorg rate directly into Aztec slot-miss rate. Deliberately-aggressive or naive proposer configurations can therefore hamper network uptime without any malice beyond bad parameter choice. *The fix is in the proposer's hands*: pick a conservatively-older L1 block within the freshness window (e.g., `block.number - 6`), trading ~6 × 12 s of additional staleness for negligible reorg probability. Sequencer client defaults MUST ship this conservatism.

**The secondary risk is app-facing.** This is also a tighter reorg surface than the existing L1→L2 inbox, which imposes a mandatory `LAG` of ≥2 checkpoints (≥~144 s) before messages in a tree become consumable -- effectively forcing L1→L2 messages to reference L1 state that is several blocks older and materially closer to finality. If a reorg bites after `propose()` has succeeded but before Ethereum has finalised the chosen block, any app proof that depended on the reorg'd L1 state becomes invalid. Bridges reading `receipts_root` via this AZIP therefore inherit a shorter buffer than bridges using the inbox.

`MIN_L1_BLOCK_LAG` could be specified as part of *this* AZIP (set, say, to 3-6 L1 blocks), enforcing proposer conservatism at the protocol level from day one and removing the dependence on client-side defaults. This AZIP does not currently propose one, on the theory that (a) sensible sequencer defaults suffice in practice, and (b) adding `MIN_L1_BLOCK_LAG` can be done later by a follow-up AZIP without breaking any deployed app. If readers of this AZIP disagree with that theory, including `MIN_L1_BLOCK_LAG` here is a cheap change.

**5. Sequencers gain a ~12-block L1 state selection window per checkpoint.** The freshness check permits the proposer to pick any L1 block within `MAX_L1_BLOCK_LAG` (~12 blocks) of the current L1 tip. Even with the monotonicity check (which prevents the committed block number from going backwards between checkpoints), the sequencer has per-checkpoint discretion over which L1 state Aztec commits to. Oracle-manipulation-sensitive apps must account for this -- the commitment alone does not prevent a sequencer picking the most-favorable-to-themselves L1 block within the window. Beyond straightforward oracle manipulation, this discretion also creates an **MEV surface**: a sequencer who operates or colludes with an Aztec app can time that app's transactions to land in the specific Aztec checkpoint whose committed L1 block is economically favorable to their position. Apps whose economic value derives from L1 state -- oracles, liquidations, auctions -- are the most exposed.

**6. Historical L1 access is sparse, not continuous.** `get_block_header_at` lets apps read the L1 block header that was committed by a *past Aztec checkpoint* -- one L1 block per checkpoint, roughly one every 72 seconds. Apps that need to prove an L1 fact from a *specific* L1 block that happens not to have been the one committed at any Aztec checkpoint (for example, proving the price at exactly L1 block 17,432,108 to settle an auction denominated in an L1 pool, or proving a specific L1 receipt emitted between Aztec checkpoints) have no direct way to do so under this AZIP. Coverage of L1 history is therefore roughly **one L1 block in six** under current parameters; the other five are unreachable. Apps needing denser coverage must either (a) proactively mirror the L1 state they care about onto the Aztec side before the relevant L1 block passes, or (b) wait for a future AZIP that exposes `parentHash` and supports chain-walking back through L1 history (see `parentHash` in the Rationale's "plausible for inclusion" list).

**7. Useful fields are deferred.** `baseFeePerGas` (a natural gas-price oracle), `requestsHash` (Pectra validator-request set), and `withdrawalsRoot` all have plausible applications and are **not** in the initial six. Adding any of them later requires either an empty-state version migration or a follow-up AZIP that breaks existing apps (see con #3).


---




## Preamble

| `azip` | `title`                | `description`                                                                            | `author`                                      | `discussions-to`                                           | `status` | `category` | `created`  |
| ------ | ---------------------- | ---------------------------------------------------------------------------------------- | --------------------------------------------- | ---------------------------------------------------------- | -------- | ---------- | ---------- |
| TBD    | L1 Block Header Access | Make L1 block header data available to Noir contracts via a single Poseidon2 commitment. | Joe Andrews (@joeandrews, joe@aztec-labs.com) | https://github.com/AztecProtocol/governance/discussions/12 | Draft    | Core       | 2026-04-17 |

## Abstract

Aztec contracts cannot read Ethereum state. This AZIP modifies the protocol so that every Aztec checkpoint commits to six fields of a recent L1 block header: `state_root`, `receipts_root`, `block_number`, `timestamp`, `prev_randao`, and `parent_beacon_block_root`. The block proposer picks the L1 block within a fixed freshness window, subject to a monotonicity check that forbids regressing the committed L1 block number between checkpoints. The six fields are stored as a single Poseidon2 commitment. Contracts open the commitment with a witness preimage and then use the individual fields for MPT proofs, receipt proofs, or beacon state proofs.

## Impacted Stakeholders

**Oracle providers.** Applications can now prove L1 state (balances, prices, events) directly against an L1 block header committed onchain per checkpoint. This is a direct substitute for oracle-relayed Ethereum data whenever the underlying source is L1 state. Existing oracles remain necessary for offchain data, multi-chain data, and low-latency feeds where checkpoint cadence plus `MAX_L1_BLOCK_LAG` is too slow.

**Token bridges, messaging bridges, intent bridges.** Bridges currently rely on the L1→L2 inbox for deposit notifications and other L1→L2 data. After this AZIP, a bridge contract can independently verify a deposit by opening a receipt proof against the committed `receipts_root`, without requiring the sequencer to pull the event through the inbox. The inbox remains available and authoritative; this adds an alternative path.

**Lending markets, restaking protocols, DeFi apps.** Lending markets that reference L1 collateral, restaking protocols that need validator information (via `parent_beacon_block_root`), and DeFi apps that reference L1 pool state can build directly against this commitment.

**Application developers (existing).** This AZIP adds a new field to the protocol interfaces: `GlobalVariables`, `BlockHeader`, `CheckpointConstantData`, `CheckpointHeader`, and `ProposedHeader`. `BlockHeader` is hashed into the `PrivateCircuitPublicInputs` and `PublicCircuitPublicInputs` expected by the kernel. All existing, deployed application circuits -- not just those that intend to use the new feature -- must therefore be recompiled against the updated ABI to remain compatible. This recompilation requirement applies to any AZIP that changes the kernel/app circuit interface; it is not unique to this proposal.

**Sequencers.** Proposing a checkpoint now requires including the L1 block header and the L1 block number as calldata. Sequencers (or rather, their Aztec node software) must track recent L1 block headers and select a recent one. Additional gas cost per `propose()` call is described in the specification.

**Provers.** The increased proving cost is negligible.

**aztec-nr maintainers.** New accessors are required on both `PrivateContext` and `PublicContext` for `l1_block_header_data_commitment`. Library helpers that open the commitment and wrap MPT / receipt / beacon-state proofs against the six fields will likely live here.

**Protocol circuit maintainers.** Changes land in all three block-root first-rollup variants (`block_root_first_rollup`, `block_root_single_tx_first_rollup`, `block_root_empty_tx_first_rollup`), in `block_rollup_public_inputs`, the merge and consecutive-block validation circuits, and the checkpoint-root composer and validator. Propagation follows the same pattern used today for `in_hash`.

**L1 contracts maintainers.** `ProposedHeaderLib.sol` gains the `l1BlockHeaderDataCommitmentSha256` field; `ProposeLib.sol` gains the RLP verification, freshness check, and `sha256ToField` computation.

**AVM team.** One new opcode -- `L1BLOCKHEADERDATACOMMITMENT` -- to expose `GlobalVariables.l1_block_header_data_commitment` to public bytecode. Gas cost, stack behavior, and error semantics are described in Specification.

**Infrastructure (RPCs, indexers, block explorers).** Serialization of `ProposedHeader`, `BlockHeader`, `CheckpointConstantData`, `CheckpointHeader`, and `GlobalVariables` all change with this AZIP. Any infrastructure deserializing these types must update coincident with the AZUP that ships this change.

## Motivation

If an Aztec contract wants to know anything about Ethereum -- a balance, a price, whether a deposit landed -- it must currently trust an oracle or poke a message through the L1→L2 inbox. Both add latency, cost, and trust assumptions.

Aztec is an Ethereum rollup, and every checkpoint already relates to an L1 block. This AZIP exposes six fields of that block's header to contracts, so any L1 state reachable through those fields can be proven with a Merkle-Patricia trie proof (or beacon-state proof), with no trust beyond L1 consensus.

## Specification

> The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119 and RFC 8174.

### Glossary

Several closely-related terms appear throughout this AZIP. They are distinct:

| Term | Meaning |
| --- | --- |
| L1 block header | The full ~20-field Ethereum L1 block header. |
| L1 block header **data** | The word **"data"** should be understood to mean the _6-field subset_ of the L1 block header this AZIP commits to: `state_root`, `receipts_root`, `block_number`, `timestamp`, `prev_randao`, `parent_beacon_block_root`. |
| L1 block header **data** commitment (Poseidon2) | Implicitly a **Poseidon2** hash of the six L1 block header data fields. What application circuits open to read an individual field because sha256 is expensive in a circuit. |
| L1 block header **data** commitment SHA256 | Explicitly the **SHA256** counterpart of the above, bound to the same six fields by the block-root first-rollup circuit. Used on L1 where Poseidon2 is expensive. |
| `L1BLOCKHEADERDATACOMMITMENT` | AVM opcode that pushes the current checkpoint's Poseidon2 L1 block header data commitment onto the operand stack. |
| `blockhash` | EVM opcode. Returns `keccak256(rlp(header_n))` for the L1 block header of block `n`. **Not** the same as the L1 block header data commitment. |
| RLP-encoded L1 block header | The L1 block header in RLP form, as passed to `propose()` calldata. `keccak256(rlpL1BlockHeader) == blockhash(n)`. |
| L1 block number | The `u64` block height of the L1 block whose header is committed. |

### What gets committed

```noir
struct L1BlockHeaderData {
    state_root: U256,          // MPT proofs for accounts, balances, storage, code
    receipts_root: U256,       // event/receipt proofs -- bridge deposit verification
    block_number: u64,         // block identification; needed for blockhash lookup
    timestamp: u64,            // L1 clock -- contracts can enforce proof freshness
    prev_randao: U256,         // beacon chain randomness -- public entropy source
    parent_beacon_block_root: U256,  // beacon chain state -- validator sets, staking
}
```

See the Rationale section for justification and discussion.

> **TODO (implementation detail): `U256` representation.** Ethereum roots are 256 bits; Noir's `Field` is BN254 (254 bits) and cannot hold a full root without truncation. The exact in-Noir representation of `U256` -- `[Field; 2]` (high/low split), `[u8; 32]`, a native 256-bit type if one is available by the time of implementation, or something else -- is deferred to the implementation PR. The choice is load-bearing: it fixes the canonical byte layout of the preimage and the Field sequence fed into `poseidon2_hash`, which must match bit-for-bit on both sides of the SHA256 → Poseidon2 boundary.

> **TODO (specification detail): canonical serialisation.** The L1-side `sha256ToField(l1BlockHeaderData)` and the Noir-side `poseidon2_hash(l1_block_header_data.serialize())` must operate on a byte-identical (for SHA256) and Field-identical (for Poseidon2) preimage. The canonical field order, byte endianness for the `u64`s, and the `U256` → byte / `U256` → `Field` conversion must be pinned down in the implementation PR and mirrored exactly in Solidity and Noir. The declaration order in the struct above is the intended canonical order; what remains is endianness and the `U256` encoding.

### Plumbing the L1 block header data commitment

We copy the "dual hashing" approach currently taken by the parity circuits to copy L1→L2 messages: SHA256 on L1 (via EVM precompile), Poseidon2 in circuits.

|                             | L1→L2 Messages             | L1 Block Header Data Commitment             |
| --------------------------- | -------------------------- | ------------------------------------- |
| **L1 side**                 | `inbox.consume()` → SHA256 | `blockhash` + RLP → `sha256ToField`   |
| **ProposedHeader**          | `inHash`                   | `l1BlockHeaderDataCommitmentSha256`                         |
| **Block root first rollup** | Parity: SHA256 + Poseidon  | Witnesses: SHA256 + Poseidon2         |
| **Propagation**             | `in_hash` through merges   | `l1_block_header_data_commitment_sha256` through merges |
| **Contract access**         | Messages in L1→L2 tree     | `l1_block_header_data_commitment` in `GlobalVariables`  |

The SHA256 check must happen at propose time because the L1 opcode `blockhash` only covers the last 256 L1 blocks; by epoch proof submission, the block may be outside this window and not accessible.

### L1 verification in `propose()`

The proposer submits the RLP-encoded L1 block header and `l1BlockNumber` as calldata. `propose()` verifies:

1. `keccak256(rlpL1BlockHeader) == blockhash(l1BlockNumber)` -- the header is real.
2. `l1BlockNumber >= block.number - MAX_L1_BLOCK_LAG` -- the header is fresh.
3. `l1BlockNumber > previousProposedHeader.l1BlockNumber` -- the committed L1 view strictly advances.
4. `sha256ToField(l1BlockHeaderData) == ProposedHeader.l1BlockHeaderDataCommitmentSha256` -- the commitment matches.

`MAX_L1_BLOCK_LAG` MUST be a hard-coded constant in the L1 rollup contract, set to `2 * AZTEC_SLOT_DURATION / ETHEREUM_SLOT_DURATION` (currently 12 blocks, ~144 seconds). Because the lag bound exceeds the minimum checkpoint cadence (~72 seconds), the freshness check alone would permit a later checkpoint to commit to an earlier `l1BlockNumber` than its predecessor. Step 3 closes that gap: the two checks together guarantee `l1BlockNumber` advances strictly at every checkpoint while remaining within the freshness window.

`ProposedHeader` gains two fields: `l1BlockHeaderDataCommitmentSha256` (`bytes32`) -- the commitment -- and `l1BlockNumber` (`uint64`) -- retained so the next proposal can enforce step 3. (`l1BlockNumber` is also committed inside `sha256ToField` as one of the six header fields; the duplicate in `ProposedHeader` exists solely to make the monotonicity check cheap on L1.)

**Genesis case.** At rollup deployment, `previousProposedHeader.l1BlockNumber` is zero. Step 3 therefore reduces to `l1BlockNumber > 0`, which is satisfied by any real L1 block.

### Rollup circuit constraints

The block root first rollup circuits (all three variants) take the 6 header fields as private witnesses and:

1. Compute `sha256ToField` → output as `l1_block_header_data_commitment_sha256` in `BlockRollupPublicInputs`.
2. Compute `poseidon2_hash` → store in `CheckpointConstantData.l1_block_header_data_commitment`.

`l1_block_header_data_commitment_sha256` propagates through block merges to the checkpoint root using the same pattern as `in_hash`: only the first block sets it, merge circuits assert the right rollup's value is 0, checkpoint root asserts nonzero. `GlobalVariables.l1_block_header_data_commitment` is populated from `CheckpointConstantData` -- same as `slot_number`, `coinbase`, `fee_recipient`, and `gas_fees`.

### `L1BLOCKHEADERDATACOMMITMENT` opcode

A new AVM environment-variable opcode that pushes `GlobalVariables.l1_block_header_data_commitment` onto the operand stack.

| Property      | Value                                                                                        |
| ------------- | -------------------------------------------------------------------------------------------- |
| Inputs        | None                                                                                         |
| Outputs       | `l1_block_header_data_commitment: Field`                                                                       |
| Gas           | Same base cost as other environment-variable opcodes (`TIMESTAMP`, `BLOCKNUMBER`, `CHAINID`) |
| Reverts       | Never                                                                                        |
| Semantics     | Returns `ExecutionEnvironment.global_variables.l1_block_header_data_commitment` unchanged                      |
| Opcode number | TBD; assigned with the implementation PR                                                     |

Public contract bytecode opens the commitment by providing the six header fields as calldata and asserting that their Poseidon2 hash equals the opcode's return value.

### Usage

**Public:** the new `L1BLOCKHEADERDATACOMMITMENT` opcode returns the current checkpoint's commitment.

**Private:** reads from `block_header.global_variables.l1_block_header_data_commitment` via archive tree membership.

**Timing within a checkpoint.** Public functions can read the current checkpoint's `l1_block_header_data_commitment` from the first block of the checkpoint onwards -- the sequencer has it in `GlobalVariables` as soon as the checkpoint's first block is being built. Private functions prove block-header membership against the archive tree; the archive tree at the start of block K contains headers up to block K-1. A private function executed in the first block of a checkpoint therefore cannot witness its own checkpoint's commitment -- the earliest private access to a checkpoint's new `l1_block_header_data_commitment` is the second block of that checkpoint. Private functions in the first block can still read any earlier checkpoint's commitment.

### Historical lookups

`get_block_header_at(l2_block_number)` returns any historical `BlockHeader` via archive tree membership. Since `l1_block_header_data_commitment` is in `GlobalVariables`, contracts can verify L1 proofs against any past checkpoint. Historical access is required to allow private storage proofs to be generated against a deterministic root, without being tied to a specific inclusion block. Public context has no historical lookup need as the sequencer is executing and the proof is constructed later when the `l1_block_header_data_commitment` is known.

```noir
fn verify_l1_storage(
    context: &mut PrivateContext,
    l2_block_number: u32,
    l1_block_header_data: L1BlockHeaderData,
    account: EthAddress,
    slot: Field,
    expected_value: Field,
    account_proof: MPTProof,
    storage_proof: MPTProof,
) {
    let header = context.get_block_header_at(l2_block_number);
    assert(poseidon2_hash(l1_block_header_data.serialize()) == header.global_variables.l1_block_header_data_commitment);
    let acct = mpt::verify_account(l1_block_header_data.state_root, account, account_proof);
    mpt::verify_storage(acct.storage_root, slot, expected_value, storage_proof);
}
```

A reference MPT implementation exists in `aztec-packages` at `noir-projects/noir-contracts/contracts/test/storage_proof_test_contract/src/storage_proofs/`.

## Rationale

### Field selection: why these six, and not others

The Ethereum post-Pectra block header (April 2026) contains 21 fields. This AZIP commits to six. The table below enumerates every header field and the reasoning for its inclusion or exclusion.

> Note: The authors are open to including more fields, as part of this AZIP, if people want.

| #   | Field                            | Introduced at                                          | Included? | Rationale                                                                                                                                                        |
| --- | -------------------------------- | ------------------------------------------------------ | --------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `parentHash`                     | Genesis                                                | No        | Omitted from the initial cut; plausible inclusion, see below. Would let apps chain back from a checkpointed L1 block through L1 history to reach L1 blocks that were not themselves directly checkpointed, which the current AZIP cannot do (historical L1 coverage is otherwise limited to the one L1 block chosen by each Aztec checkpoint proposer -- roughly one L1 block in six).                                                                                  |
| 2   | `ommersHash`                     | Genesis                                                | No        | Frozen to `keccak(rlp([]))` post-Merge; carries no information.                                                                                                  |
| 3   | `beneficiary` (coinbase)         | Genesis                                                | No        | MEV attribution rarely needed in-circuit; can be proven via receipt log if required.                                                                             |
| 4   | **`stateRoot`**                  | Genesis                                                | **Yes**   | MPT proofs for accounts, balances, storage slots, code hashes. Core use case.                                                                                    |
| 5   | `transactionsRoot`               | Genesis                                                | No        | Receipts (via `receiptsRoot`) dominate: they include tx status and log emissions. Covering both doubles the preimage for limited marginal benefit.               |
| 6   | **`receiptsRoot`**                | Genesis                                                | **Yes**   | Event / log inclusion proofs -- needed for bridge deposit verification and event-driven L2 logic.                                                                 |
| 7   | `logsBloom`                      | Genesis                                                | No        | Probabilistic filter; its value is in offchain filtering, not in-circuit checks.                                                                                 |
| 8   | `difficulty`                     | Genesis                                                | No        | Frozen to 0 post-Merge.                                                                                                                                          |
| 9   | **`number`**                     | Genesis                                                | **Yes**   | Block identification; required to cross-reference with `blockhash(l1BlockNumber)` at propose time and to resolve the preimage to a known L1 block.               |
| 10  | `gasLimit`                       | Genesis                                                | No        | Not needed for application-level L1 state proofs.                                                                                                                |
| 11  | `gasUsed`                        | Genesis                                                | No        | Not needed for application-level L1 state proofs.                                                                                                                |
| 12  | **`timestamp`**                  | Genesis                                                | **Yes**   | L1 clock; lets contracts enforce freshness bounds on L1 proofs.                                                                                                  |
| 13  | `extraData`                      | Genesis                                                | No        | Free-form sequencer-set field; no protocol semantics.                                                                                                            |
| 14  | **`prevRandao`** (`mixHash`)     | Genesis; semantics changed at Merge (EIP-4399)         | **Yes**   | Public entropy from the beacon chain; useful for randomness-sensitive apps.                                                                                      |
| 15  | `nonce`                          | Genesis                                                | No        | Frozen to 0 post-Merge.                                                                                                                                          |
| 16  | `baseFeePerGas`                  | London (EIP-1559, Aug 2021)                            | No        | A gas-price oracle with obvious L2 applications. Omitted from the initial cut for minimality; see below.                                                         |
| 17  | `withdrawalsRoot`                | Shanghai (EIP-4895, Apr 2023)                          | No        | Validator withdrawal data; overlaps with `parentBeaconBlockRoot` for the restaking audience.                                                                     |
| 18  | `blobGasUsed`                    | Cancun (EIP-4844, Mar 2024)                            | No        | Blob-market-specific; narrow audience.                                                                                                                           |
| 19  | `excessBlobGas`                  | Cancun (EIP-4844, Mar 2024)                            | No        | Blob-market-specific; can be added later via a separate AZIP if demand arises.                                                                                   |
| 20  | **`parentBeaconBlockRoot`**      | Cancun (EIP-4788, Mar 2024)                            | **Yes**   | Bridge to beacon chain state -- validator set, staking data, sync committees. Critical for restaking.                                                             |
| 21  | `requestsHash`                   | Pectra (EIP-7685, May 2025)                            | No        | Consolidated consensus-layer requests (deposits, withdrawals, consolidations). Useful for validator-tracking apps; omitted from the initial cut.                 |

**Fields with a plausible case for inclusion that this AZIP defers:**

- **`parentHash`** -- the keccak hash of the previous L1 block's RLP-encoded header. Including it would let apps **walk L1 history backwards from a committed block** by supplying the full RLP of the parent block as a witness, hashing it in-circuit, and checking it against the committed `parentHash` -- then repeating, to reach any L1 block older than a given checkpoint's committed block. This directly addresses the sparse-historical-coverage limitation (only ~1 in 6 L1 blocks is reachable under this AZIP, since each Aztec checkpoint commits just one L1 block out of every ~6 produced): with `parentHash` included, an app needing to prove a fact from a specific L1 block that was *not* a checkpoint-committed one (e.g., "the L1 price at exactly L1 block 17,432,108") can chain from the nearest later committed block down to the target block, bounded only by how many hash-and-check steps the app is willing to pay for. Trade-off: each chain step costs one in-circuit keccak over the parent's RLP header (~25k+ gates per step using current Noir keccak), and in-circuit RLP extraction of the parent's `parentHash` field. Expensive per step, but it turns the "one L1 block in six" historical coverage problem into "any L1 block, at linear cost in distance."
- **`baseFeePerGas`** -- a pricing oracle that is natively available on every L1 block. Applications for cross-chain gas estimation and relative-fee oracles are obvious. Trade-off: inflates the preimage and therefore every in-circuit Poseidon2 opening.
- **`requestsHash`** -- exposes the Pectra request set (deposits, withdrawals, consolidations). Audience is currently narrow but the restaking / validator-tracking use case is real.
- **`withdrawalsRoot`** -- partial substitute for `requestsHash` for validator tracking; the two are overlapping enough that including both would be redundant for most applications.

These were excluded from the initial cut for minimality. Any of them can be added by a future AZIP, **subject to the forward-compatibility constraints discussed in Security Considerations** -- in practice, adding fields to this commitment is a breaking change for every deployed private circuit that reads it.

**Why receipts root over transactions root.**

Receipts commit both to transaction status and to emitted logs. Transactions commit only to inputs, which is usually less useful for in-contract verification.

**Why six fields rather than all ~20.**

> Note: The authors are open to including more fields, as part of this AZIP, if people want.

Committing to every field in the full L1 block header, rather than just six, would let applications read any field without future AZIPs. The costs scale in two places:

- **SHA256 in the block-root first-rollup circuit.** SHA256 costs ~4,000 gates per 64-byte compression block (empirical, current Noir / Barretenberg UltraHonk). The six-field preimage encodes to ~144 bytes → 3 blocks → **~12,000 gates**. An ~20-field preimage encodes to roughly the same content as the RLP body minus per-field RLP overhead (~500 bytes) → ~8-9 blocks → **~32,000-36,000 gates**. Delta: **~20,000-24,000 added gates per checkpoint**, paid once in the rollup pipeline.
- **Poseidon2 opening in every application circuit that reads the commitment.** The empirical six-field opening is **~150 gates**. A ~20-field opening scales roughly linearly with preimage size to **~500-600 gates**. Delta: **~350-450 added gates per application proof** that reads L1 state.

The SHA256 delta is paid once per checkpoint and is small relative to total proving cost. The Poseidon2 delta is paid by *every* application proof and is the figure that dominates at ecosystem scale. Field selection is therefore driven by minimising the per-proof opening cost -- only fields with concrete cross-use-case demand are included.

### Single Poseidon2 commitment vs. six individual `GlobalVariables` fields

Exposing the six fields as separate `GlobalVariables` entries was considered and rejected:

- Six extra `Field`s in every `BlockHeader` hash, recomputed on every membership lookup.
- Six new AVM opcodes (one per field).
- Six new fields propagated through every rollup circuit layer.

A single commitment costs one opcode, one field through the circuits, and one hash in `BlockHeader`. Applications pay one Poseidon2 opening (~150 gates) exactly when they use the feature, and the ABI surface is narrower and easier to audit.

### Gas analysis

| Operation                                   | Gas        |
| ------------------------------------------- | ---------- |
| RLP header calldata (~550 bytes)            | ~9,000     |
| `l1BlockNumber` calldata (8 bytes)          | ~128       |
| `keccak256` over RLP header                 | ~130       |
| `blockhash` + `block.number`                | 22         |
| Field extraction (6 × `calldataload`)       | ~350       |
| `sha256` precompile (~192 bytes)            | ~160       |
| Previous `l1BlockNumber` SLOAD (warm)       | ~100       |
| `previousProposedHeader.l1BlockNumber` cmp  | ~3         |
| **Total**                                   | **~9,893** |

One warm SLOAD, no SSTORE beyond existing `ProposedHeader` writes (the new `l1BlockNumber` field packs into an existing slot). Under 3% of existing `propose()` cost.

### Dual-hash: SHA256 + Poseidon2

The SHA256 side is necessary because the L1 verification in `propose()` runs in Solidity, where SHA256 is a 160-gas precompile and Poseidon2 would cost millions of gas. The Poseidon2 side is necessary because application circuits open the commitment inside Noir, where Poseidon2 is ~150 gates and keccak/SHA256 are ~25k+ gates. The block-root first-rollup circuit constrains both hashes against the same six witness values.

This is the same dual-hash pattern already used for L1→L2 messages via the parity circuits; reusing it keeps the verification surface uniform.

### Freshness bound `MAX_L1_BLOCK_LAG`

Set to `2 * AZTEC_SLOT_DURATION / ETHEREUM_SLOT_DURATION` (12 L1 blocks, ~144s at current parameters).

Without a freshness check, a sequencer could reference any L1 block within the 256-block `blockhash` window (~51 minutes of staleness) and manipulate oracle-style applications by picking the block whose state was most favorable to a particular trade. The chosen bound is tight enough to make such manipulation negligible while loose enough to survive ordinary L1 reorgs and slot misses.

### Monotonicity of `l1BlockNumber`

This AZIP's `propose()` verification includes a monotonicity check: `l1BlockNumber > previousProposedHeader.l1BlockNumber`.

#### Strict `>` rather than `>=`?

`>` rather than `>=` is recommended because it has a cleaner semantic (L1 time strictly advances), it is trivially satisfiable under current parameters (`AZTEC_SLOT_DURATION / ETHEREUM_SLOT_DURATION ≈ 6`, so every new checkpoint has several new L1 blocks to choose from), and it matches the user intuition that each Aztec checkpoint corresponds to a *distinct* L1 state.

### Freshness enforced in `propose()` rather than at proof submission

`blockhash` is only accessible for the last 256 L1 blocks. By the time an epoch proof is submitted, the chosen L1 block may be outside this window and no longer callable. The check must therefore happen at propose time.

### Lag between L1 block production and Aztec-function readability

At current parameters (L1 block = 12 s, Aztec block = 6 s, Aztec checkpoint = 72 s), readability lag has a tight lower bound. `l1_block_header_data_commitment` is fixed per checkpoint: all Aztec blocks within a checkpoint see the same commitment, chosen by the proposer from within `MAX_L1_BLOCK_LAG` (144 s) of the L1 tip.

**Public functions** read `l1_block_header_data_commitment` from the first Aztec block of the committing checkpoint -- the sequencer populates `GlobalVariables` at the moment that block begins being built. If L1 block N is produced right as a new checkpoint starts and the proposer commits it, a public function in that first Aztec block reads N's data immediately, for a best-case lag of **0 s**.

**Private functions** prove membership against the archive tree, which at the start of Aztec block K contains headers only up to block K-1. A private circuit in the first Aztec block of a checkpoint therefore *cannot* witness that checkpoint's new commitment -- no header carrying the new value is in the archive tree yet. The earliest private access is the *second* Aztec block of the checkpoint, one Aztec-block period later, for a best-case lag of **~6 s** (public + one Aztec block).

If the proposer instead picks a conservatively-older L1 block within the freshness window (for reorg-resistance -- see con #4), the lag grows correspondingly: up to **~144 s** at the far end of `MAX_L1_BLOCK_LAG`, bounded below by monotonicity against the previous checkpoint's committed L1 block.

### Alternative design: L1 read requests through the kernel

An alternative design was considered in which private functions would not open the commitment directly. Instead they would emit L1 read requests -- of the shape `{ claimed_data_field: Field, claimed_data_field_id: u32 }` -- as part of `PrivateCircuitPublicInputs`, the same way they currently emit note read requests and key validation requests. The private kernel would resolve each request against the current checkpoint's commitment and discharge it before the public inputs are exposed.

**Advantages:**

- **Forward compatibility.** If the commitment preimage is later extended (e.g. adding `baseFeePerGas`), existing deployed private circuits continue to work. They only know how to request the fields they already understand; new field IDs can be allocated without changing `PrivateCircuitPublicInputs`. The only circuit that needs to update is the kernel.
- **ABI stability.** The kernel/app interface is decoupled from the preimage layout.
- **Tractable deprecation.** Fields can be removed from the commitment, or their semantics changed (e.g. a future Ethereum fork repurposes a slot), by deprecating field IDs -- existing apps that request those IDs can be gracefully rejected rather than silently producing wrong answers.

**Disadvantages:**

- **Kernel complexity.** The private kernel is one of the most constraint-heavy and audit-critical circuits in the protocol. Adding a new read-request pipeline carries substantial implementation and review cost.
- **Kernel proving time.** All transactions pay for the capacity even if they do not use L1 data.

### L1 hard-fork stranding risk, and why this AZIP accepts it

The direct-opening-within-a-private-function design is structurally exposed to Ethereum hard-forks that change either the semantics of the six committed fields or the structure of the trees those fields address. This subsection documents *why* the AZIP accepts that exposure, rather than waiting for a design that avoids it.

The design choice is between:

- **Option A -- ship this AZIP's direct-opening design now.** Apps get L1 state access immediately, cheaply, with a clean audit surface. Apps break at the first Ethereum fork that changes any committed field's semantics. Recovery under the current protocol architecture is application-level only: upgradeable apps ship new `class_id`s; immutable apps or apps with L1-gated exits remain stranded.
- **Option B -- delay until two prerequisites are both in place.** (i) The "L1 read requests through the kernel" design (see the previous Rationale subsection), which moves preimage interpretation into the private kernel so that changes in Ethereum format can be absorbed there. (ii) A mechanism for updating protocol-circuit verification keys, so the kernel can actually be redeployed when Ethereum changes. **Neither prerequisite currently exists**, and the second is politically load-bearing: many protocol stakeholders actively oppose giving any actor -- including governance -- the power to change what the kernel accepts as a valid proof, because that power could be used to change what "valid" means for existing chains. A VK-update mechanism acceptable to the ecosystem is an open research question, not a scheduled engineering task. Cost: a substantial private-kernel rewrite *plus* resolving the VK-update governance question. If either prerequisite fails to ship, Option B delivers none of its benefits.

This AZIP chooses Option A. The reasoning:

1. **Ethereum's most disruptive scheduled changes have multi-year lead time.** The biggest near-term breaker -- state-trie migration to a Verkle tree, and later to a SNARK-friendlier commitment -- is a long-running Ethereum research programme with no fixed activation date at the time of writing. Aztec has time to pursue Option B's prerequisites in parallel with the lifetime of this AZIP.

2. **Option B shipped later *may* retire the stranding problem permanently -- if the prerequisites can be met.** If both the kernel-delegation design and the VK-update mechanism are in place before the first format-breaking Ethereum fork, the stranding-risk window is bounded to the period between this AZIP's activation and Option B's activation. That is a real and significant benefit. It is, however, contingent on the VK-update governance question being answered -- which it currently is not.

3. **The cost of not shipping this AZIP is real and accruing.** Every month without in-circuit L1 state access is a month in which apps lean on centralized oracles and bespoke L1→L2 message hacks. Those costs accrue to end users through trust assumptions and worse UX. Waiting for Option B before shipping anything would exchange a hypothetical future migration (Option A's downside) for a certain present cost -- and, given the unresolved VK-update question, possibly forever.

4. **The app-level recovery path covers the majority case.** Most plausible L1-reading apps can be built as upgradeable contracts with L1-read-free exit paths. Such apps handle a format-breaking Ethereum fork by shipping a new `class_id` that understands the new format; users transact against the upgraded class, and funds are not stranded. The stranding problem bites hardest in a narrower set of designs -- immutable apps, or apps whose upgrade or exit paths are themselves L1-gated -- and these are design choices app developers can make with full knowledge of the trade-off.

**Recommended posture:**

> This recommendation is weakly held. The cons of this azip should be debated.

Ship this AZIP; track Ethereum's fork calendar closely; in parallel, pursue (i) the design and implementation of L1-read-request kernel delegation, and (ii) ecosystem consensus on a VK-update mechanism for protocol circuits. Aim to have both resolved before the first format-breaking Ethereum fork activates. If either prerequisite remains unresolved at the time of such a fork, the fallback is necessarily application-level: affected apps ship `class_id` upgrades, users migrate to the upgraded class, and apps that were deployed without preserving L1-read-free exits or without upgradeability accept permanent stranding for their users' L1-reading functionality.

The residual risk accepted by this AZIP is the interval between now and Option B's activation -- an interval whose length is currently unbounded on the upside because of the open VK-update question. During that interval, any Ethereum format change produces the stranding scenario described above. **A subset of that risk is indefinite, not merely delayed**: if an app is immutable, if its exit path depends on L1 reads, or if its upgrade instigation depends on L1 reads, users cannot self-recover. Mitigations are application-level:

- Apps that hold user funds and depend on L1 reads **MUST** preserve at least one exit path that does not itself depend on L1 reads -- a governance-triggered emergency withdrawal, a pre-signed exit, or a path that uses only data the app already stored on its own Aztec side. This is the only application-layer defence against exit-blocked stranding.
- Apps holding user funds SHOULD deploy as upgradeable (non-immutable) rather than immutable, unless they provably do not depend on L1 reads for any current or foreseeable functionality. Immutability plus L1-read dependency is a combination whose accepted risk is permanent stranding at the next Ethereum format change.
- For upgradeable apps, upgrade governance SHOULD NOT itself depend on L1 reads -- otherwise an L1 format change blocks the very upgrade that would fix the problem.
- User-facing wallets SHOULD surface Aztec version and class-id compatibility information so users can make informed decisions about which app versions to interact with.
- Aztec governance SHOULD prepare an emergency AZUP process that can directly address bricked app state if a fast Ethereum change surprises the ecosystem before Option B's prerequisites are resolved -- recognizing that this itself is a politically weighty capability.

### Alternative design: beacon-root-only commitment (reach everything via SSZ)

A second alternative was considered in which Aztec would commit only to the beacon block root -- one 32-byte value -- and applications would reach every EL header field, and all beacon-chain state, via SSZ Merkle proofs from that root. No `L1BlockHeaderData` preimage; no dual-hash bridge; just one hash.

#### Why it is even possible

SSZ (Simple Serialize) is the canonical encoding for beacon-chain data. Every container is Merkleized with a fixed, type-determined layout: each field sits at a stable generalized index, and any field's value can be proven against the container's `hash_tree_root` with a Merkle path of SHA256 hashes. Beacon-chain data therefore behaves like one large Merkle tree rooted at the beacon block root.

Crucially, the post-Cancun beacon block contains the execution-layer payload inside its body:

```
BeaconBlock
├── slot, proposer_index, parent_root
├── state_root                          ← BeaconState root (validators, balances, RANDAO, slashings, …)
└── body: BeaconBlockBody
    ├── randao_reveal, eth1_data, graffiti
    ├── proposer_slashings, attester_slashings, attestations, deposits, voluntary_exits
    ├── sync_aggregate
    ├── execution_payload: ExecutionPayload  (its hash_tree_root enters the body's SSZ tree)
    │   ├── parent_hash, fee_recipient
    │   ├── state_root                   ← EL state root
    │   ├── receipts_root                ← EL receipts root
    │   ├── logs_bloom, prev_randao
    │   ├── block_number, gas_limit, gas_used, timestamp, extra_data, base_fee_per_gas
    │   ├── block_hash, transactions_root, withdrawals_root
    │   ├── blob_gas_used, excess_blob_gas
    │   └── …
    ├── bls_to_execution_changes, blob_kzg_commitments
    └── execution_requests   (Pectra)
```

So every EL field this AZIP commits to -- `state_root`, `receipts_root`, `block_number`, `timestamp`, `prev_randao` -- is also reachable from the beacon block root via an SSZ proof, alongside the entire beacon state (validator set, balances, sync committees, slashings, withdrawals).

#### What `parentBeaconBlockRoot` actually points to, and the extra staleness

EIP-4788 (Cancun, 2024) is the mechanism that exposes a beacon block root to the EL. Its name is precise but easy to misread:

- For the EL block at slot S, `parentBeaconBlockRoot = hash_tree_root(BeaconBlock_{S-1})`.
- `BeaconBlock_{S-1}` contains the `execution_payload` for EL block at slot S-1.

So if Aztec commits `parentBeaconBlockRoot` read from L1 block X, any EL field an app extracts via SSZ proofs belongs to **EL block X − 1**, not X. That is **one Ethereum slot (~12 s) of additional staleness** relative to reading X's header directly -- which is what the six-field design in this AZIP does. Stacked on top of `MAX_L1_BLOCK_LAG`, the worst-case committed EL state becomes ~156 s old instead of ~144 s.

#### L1-side cost

EIP-4788 stores recent beacon roots in a ring-buffer contract at `0x000F…Beac02`, keyed by timestamp. `propose()` would query it rather than parse RLP:

| Operation                                     | Gas       |
| --------------------------------------------- | --------- |
| Timestamp calldata (8 bytes)                  | ~128      |
| `CALL` to beacon roots contract (warm)        | ~100      |
| SLOAD inside beacon roots contract            | ~2,100    |
| Freshness / monotonicity checks               | ~200      |
| **Total**                                     | **~2,500**|

Roughly **~7 k gas cheaper per `propose()`** than the hybrid design in this AZIP -- a negligible saving in rollup economics (<0.1% of `propose()` cost).

#### App-side cost: the reason this design is rejected

SSZ proofs use SHA256. Empirically measured in current Noir / Barretenberg UltraHonk (via a simple benchmark circuit that chains N SHA256 calls and linear-regresses the gate count), one SHA256 compression -- one application of the 64-round core to a 64-byte block -- costs **~4,000 gates**. Each SSZ sibling-hash step concatenates two 32-byte hashes to form 64 bytes of input; with SHA256's mandatory padding (1-bit + zero-fill + 8-byte length) this crosses the 64-byte boundary and requires **two compressions ≈ 8,000 gates per sibling-hash step**.

Path depth from beacon block root to an EL payload field (April 2026 Pectra specs):

| Container                 | Fields | Padded | Tree depth |
| ------------------------- | ------ | ------ | ---------- |
| `BeaconBlock`             | 5      | 8      | 3          |
| `BeaconBlockBody`         | 13     | 16     | 4          |
| `ExecutionPayloadHeader`  | 17     | 32     | 5          |

Total ≈ **12 sibling-hash steps ≈ 96,000 gates** to extract a single EL header field, *before* the MPT proof on top. A single Poseidon2 opening of this AZIP's six-field commitment is empirically **~150 gates**. That is a **~640× cost difference**, paid on **every** application proof that reads L1 state -- which is the whole point of this AZIP.

For beacon-state access (validator balances, committee membership) the SSZ cost is similar in both designs: the ~96k-gate path to `BeaconState` is unavoidable either way because the validator registry is itself a deep SSZ list that must be walked with SHA256.

#### Forward-compatibility posture

SSZ has a specific stability property: the generalized index of existing fields is determined by declaration order and the container's padded size. Adding a field that stays under the next power-of-2 boundary keeps all existing generalized indices stable; adding a field that crosses the boundary re-pads the tree and invalidates all existing proofs.

Examples:

- `BeaconBlockBody` currently has 13 fields (padded to 16). Fields 14, 15, 16 could be added safely. A 17th field would re-pad to 32 and invalidate every SSZ proof against the body.
- `ExecutionPayloadHeader` has 17 fields (padded to 32). It has 15 slots of headroom.

EIP-7688 ("stable containers") is a live proposal to make these guarantees explicit for beacon types, but is not shipped as of April 2026. Until it does, a beacon-root-only design inherits Ethereum's SSZ-repadding risk -- qualitatively similar to the preimage-layout risk this AZIP's direct design carries, and in neither case are apps immune to Ethereum restructuring their state root (e.g., the Verkle / SNARK-friendly migration).

#### What the current design already carries over from this alternative

`parent_beacon_block_root` **is one of the six fields this AZIP already commits to**. Apps that need beacon-state access -- restaking, validator tracking, sync-committee-driven logic -- can already do SSZ proofs against that field with the same ~12 s staleness and the same ~600k-gate budget the beacon-only alternative would have. The other five fields (state_root, receipts_root, block_number, timestamp, prev_randao) are a pure optimization layer: they short-circuit the SSZ tax for the EL data that is most commonly needed.

So the beacon-only alternative is not an orthogonal design -- it is a strict subset of this AZIP:

|                              | Beacon-root-only                      | This AZIP (hybrid)                         |
| ---------------------------- | ------------------------------------- | ------------------------------------------ |
| L1 commitment size           | 32 bytes                              | 32 bytes (Poseidon2 of 6 fields)           |
| L1 gas / `propose()`         | ~2.5 k                                | ~9.9 k                                     |
| EL field access cost         | ~96 k gates (SSZ)                     | ~150 gates (Poseidon2 opening)             |
| Beacon-state access cost     | ~96 k gates to reach `BeaconState`    | ~96 k gates via `parent_beacon_block_root` |
| EL data staleness            | + one L1 slot (~12 s)                 | current L1 block (no extra lag)            |
| Forward-compat risk          | SSZ repadding                         | Preimage layout                            |

**Conclusion.** Beacon-root-only saves ~7 k L1 gas per checkpoint in exchange for a ~640× increase in per-proof gate cost on the common case and 12 s of extra staleness on any EL data. The current AZIP already gives apps the beacon-root escape hatch for the niche case (via `parent_beacon_block_root`), while preserving the cheap direct path for the common case. Adopting the beacon-only design would remove the short-circuit without adding any capability the current design lacks.

### Alternative design: app-layer L1 block header copier via L1→L2 messages

L1 block header data could instead be exposed to Aztec apps without any protocol change: a third party deploys an Aztec contract -- an "L1 block header copier" -- with an accompanying L1 portal that reads `blockhash(targetBlock)` and forwards the header (or a commitment to it) through the existing L1→L2 inbox. Consuming apps read the data via cross-contract calls or by proving membership in the L1→L2 messages tree.

This is available today and requires no AZIP. It is rejected as the *default* path for L1 state access because it pushes the keccak/RLP cost back onto every consuming circuit, adds inbox latency, leaves freshness and monotonicity unenforced, and creates one trust-and-liveness dependency per copier deployment -- each of which consuming apps must individually audit. A single audited protocol primitive shared across all consumers is cheaper per-proof and has a smaller aggregate trust surface. The app-layer path remains available as a complement for niche cases (e.g. bridges with a dedicated copier) where those trade-offs are acceptable.

## Backwards Compatibility

This AZIP introduces the following backwards incompatibilities:

1. **Block format.** `GlobalVariables`, `BlockHeader`, `CheckpointConstantData`, `CheckpointHeader`, and `ProposedHeader` each gain a new `l1_block_header_data_commitment` field. Serialization byte layouts change. Indexers, archive nodes, block explorers, and any infrastructure deserializing these types must update coincident with the AZUP that activates this AZIP.

2. **Application circuit ABI.** `BlockHeader` is hashed into the kernel's view of every application circuit. Changing `BlockHeader` changes the `PrivateCircuitPublicInputs` and `PublicCircuitPublicInputs` structure expected by the kernel. Every deployed application circuit -- including circuits that never read L1 state -- must be recompiled against the new ABI to remain compatible. There is no runtime opt-out.

3. **`propose()` calldata.** Proposers must submit the RLP-encoded L1 block header and the L1 block number with every checkpoint proposal. Sequencer software that does not include this data will have its proposals rejected by the L1 rollup contract.

Activation is via AZUP. Existing *application logic* is unaffected; only circuit compilation artifacts change.

## Test Cases

1. **Correct commitment.** 6 header fields as witnesses → `poseidon2_hash(fields) == context.l1_block_header_data_commitment()`.
2. **Storage proof.** MPT proof against opened `state_root`.
3. **Receipt proof.** Event inclusion against opened `receipts_root`.
4. **Beacon state proof.** Validator data against opened `parent_beacon_block_root`.
5. **Historical lookup.** Past checkpoint's `l1_block_header_data_commitment` via `get_block_header_at()`.
6. **Invalid commitment.** Mismatched `sha256ToField` → revert.
7. **Out-of-range block.** `l1BlockNumber` outside `blockhash` window → revert.
8. **Stale block.** `l1BlockNumber < block.number - MAX_L1_BLOCK_LAG` → revert.
9. **Non-monotonic block.** `l1BlockNumber <= previousProposedHeader.l1BlockNumber` → revert, including the equality case.
10. **Genesis proposal.** First `propose()` after deployment succeeds against `previousProposedHeader.l1BlockNumber == 0` for any real L1 block.

## Scope of Changes

**L1 Contracts:** `ProposedHeaderLib.sol` (add `l1BlockHeaderDataCommitmentSha256`, `l1BlockNumber`), `ProposeLib.sol` (RLP verification, freshness check, monotonicity check against `previousProposedHeader.l1BlockNumber`, `sha256ToField`).

**Noir Types:** `global_variables.nr`, `checkpoint_constant_data.nr`, `checkpoint_header.nr` (add `l1_block_header_data_commitment`), `constants.nr` (update lengths).

**Noir Rollup:** `block_root_first_rollup.nr` / `block_root_single_tx_first_rollup.nr` / `block_root_empty_tx_first_rollup.nr` (add witnesses, compute hashes), `block_rollup_public_inputs.nr` (add `l1_block_header_data_commitment_sha256`), `block_rollup_public_inputs_composer.nr` (populate from constant data), `merge_block_rollups.nr` (propagate left), `validate_consecutive_block_rollups.nr` (assert right == 0), `checkpoint_rollup_public_inputs_composer.nr` / `checkpoint_root_inputs_validator.nr` (populate / assert nonzero).

**Noir Libraries:** `public_context.nr`, `private_context.nr`, `avm.nr` (add `l1_block_header_data_commitment()` accessor).

**Sequencer:** `global_builder.ts` (compute Poseidon2), `checkpoint_proposal_job.ts` (include RLP calldata), `checkpoint_header.ts` (add field).

## Security Considerations

**Proposer liveness under L1 reorgs (primary concern).** The freshness bound permits the proposer to reference an L1 block as recent as `block.number - 1` (~12 s old). Very recent L1 blocks have non-negligible reorg probability under Ethereum's probabilistic finality -- full finality arrives only after two epochs (~12.8 min). If the proposer commits to an L1 block that is reorged out before `propose()` is included, step 1 of `propose()` (`keccak256(rlpL1BlockHeader) == blockhash(l1BlockNumber)`) fails, the transaction reverts, and the L2 slot is wasted. A proposer population that consistently picks the freshest permissible L1 block converts ambient L1 reorg rate directly into Aztec slot-miss rate, degrading network throughput. Sequencer client defaults MUST pick a conservatively-older L1 block within the freshness window (e.g., `block.number - 6`), not the freshest permissible one.

**L1 reorgs affecting application proofs (secondary concern).** If the chosen L1 block is reorged out *after* `propose()` lands (i.e., the `propose()` tx's L1 block itself gets reorged), application proofs that depend on the reorg'd L1 state become invalid. This is a tighter reorg surface than the existing L1→L2 inbox exposes. The L1→L2 inbox imposes a mandatory `LAG` of ≥2 checkpoints (≥~144 s) before messages in a tree become consumable, which in effect forces messages to reference L1 state that is already several L1 blocks old and materially closer to finality. Bridges reading L1 state via `receipts_root` under this AZIP inherit the shorter buffer. High-value applications SHOULD wait for L1 finality before relying on L1 proofs, or SHOULD enforce `l1_block_header_data.timestamp`-based windows that sit within finality. A future AZIP MAY introduce a `MIN_L1_BLOCK_LAG` to force proposer selections away from the most-recent few L1 blocks at the protocol level.

**Staleness of L1 block.** The committed L1 block may lag the current L1 tip by up to `MAX_L1_BLOCK_LAG` (~144s) plus one Aztec slot (~72s). Contracts MAY enforce tighter bounds via `l1_block_header_data.timestamp`.

**Sequencer block selection.** Within `MAX_L1_BLOCK_LAG`, and subject to strict monotonicity against the previous checkpoint's `l1BlockNumber`, a sequencer chooses which L1 block to reference. In the common case this is ~12 blocks to pick from. Applications that rely on a specific L1 state transition being captured by a specific Aztec checkpoint MUST account for this selection window. Monotonicity guarantees the committed `l1BlockNumber` never regresses between checkpoints; it does not constrain *how far* each checkpoint advances, so a single checkpoint can still skip across multiple L1 blocks within the lag.

**Sequencer withholding.** A sequencer can refuse to propose, which is a pre-existing liveness property and no worse under this AZIP.

**L1 liveness coupling.** Aztec liveness now has an explicit dependency on recent L1 block header availability. An L1 outage exceeding `MAX_L1_BLOCK_LAG` plus the checkpoint interval would halt checkpoint production. The existing requirement that checkpoints land via L1 `propose()` already dominates this coupling in practice; the new requirement does not widen the failure surface meaningfully.

**MPT proof correctness.** Application security depends on the correctness of the Noir MPT library used to open storage and receipt proofs. Reference implementations MUST be audited before apps deploy against them.

**Constraint completeness of the SHA256→Poseidon2 binding.** The block-root first-rollup circuit MUST fully constrain both hashes against the same six witness values. A soundness bug here could let a malicious prover bind the commitment to fields that do not match the L1 block. This circuit MUST be audited jointly with the L1 `propose()` verification.

**Forward compatibility.** The six-field preimage is effectively frozen for the lifetime of the protocol version that ships it. Private function circuits are standalone Noir circuits: they embed the preimage layout as hard-coded constraints. If a future AZIP adds, removes, or reorders fields in the preimage, every deployed private circuit that reads this commitment is bricked. Two classes of change are of concern:

> **Ethereum changes the header.** The header has changed repeatedly in recent history. At The Merge (September 2022, EIP-3675 / EIP-4399), `mixHash` was repurposed as `prevRandao`: the field position was unchanged, but its semantic source changed completely. At the same time, `difficulty`, `nonce`, and `ommersHash` were frozen to constants. Subsequent forks added entirely new fields: `baseFeePerGas` (EIP-1559, London), `withdrawalsRoot` (EIP-4895, Shanghai), `blobGasUsed` and `excessBlobGas` (EIP-4844, Cancun), `parentBeaconBlockRoot` (EIP-4788, Cancun), and `requestsHash` (EIP-7685, Pectra). Any similar future addition or semantic change affects this AZIP's preimage or the meaning of the values it carries.
>
> Of the fields this AZIP commits to, the most at-risk on the current Ethereum roadmap is `stateRoot`. Proposals to move Ethereum to a SNARK-friendlier state commitment (Verkle trees, then eventually a Poseidon / polynomial commitment) would change what `stateRoot` is and break deployed MPT proofs. Other roadmap items with header implications include post-quantum migration on the beacon chain (changing how `parentBeaconBlockRoot` is computed), enshrined PBS, and additions to the `requestsHash` request set. `timestamp`, `block_number`, `receiptsRoot`, and `prevRandao` are lower-risk but not guaranteed stable.
>
> **Aztec changes the preimage.** The safe upgrade point is a major Aztec version bump with empty state -- a new network instance, where no deployed private circuit depends on the old preimage. Mid-version preimage changes are unsafe for private circuits regardless of whether fields are added, removed, or reordered. Public functions can in principle adapt to mid-version changes (they re-execute each block against current bytecode), but that does not rescue private circuits whose constraints are baked in at compile time. Applications SHOULD assume the preimage is stable only for the duration of the protocol version that introduces it.
>
> The "L1 read request" alternative design (see Rationale) is materially more forward-compatible and remains a candidate for a follow-up AZIP if future Ethereum header changes arrive on a cadence that makes app-recompilation burdensome.

## Copyright Waiver

Copyright and related rights waived via [CC0](/LICENSE).
