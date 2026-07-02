# AZIP-22: Fast Inbox

## Preamble

| `azip` | `title`    | `description`                                                                                                                         | `author`                                                  | `discussions-to`                                           | `status` | `category` | `created`  |
| ------ | ---------- | ------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------- | ---------------------------------------------------------- | -------- | ---------- | ---------- |
| 22     | Fast Inbox | Streams L1-to-L2 messages into blocks as they arrive on the Inbox rather than batching them per checkpoint, reducing message latency. | Santiago Palladino (@spalladino, santiago@aztec-labs.com) | https://github.com/AztecProtocol/governance/discussions/53 | Draft    | Core       | 2026-07-01 |

## Abstract

Today, all L1-to-L2 messages for a checkpoint are added at its start, yielding a message latency of between 24 and 108 seconds. This AZIP streams L1-to-L2 messages into L2 blocks as they are received by the Inbox, rather than waiting for an Inbox tree to be sealed in order to inject all its messages simultaneously at the beginning of the next checkpoint. The Inbox is redesigned to commit to received messages via a rolling hash snapshotted per L1 block, checkpoints reference the last message bucket they consume, and an `INBOX_LAG_SECONDS` lag guards against shallow L1 reorgs. The result reduces message latency to between 12 and 30 seconds.

## Impacted Stakeholders

This proposal affects **sequencers and proposers**, who now insert L1-to-L2 messages into each block as they build it and choose which Inbox buckets a checkpoint consumes; **validators**, who validate the message bundle carried by each block proposal and enforce the censorship and lag rules before attesting; and **users and applications sending L1-to-L2 messages**, who benefit from reduced message latency and are subject to the per-block and per-checkpoint message caps.

## Motivation

### How L1-to-L2 messages work today

L1-to-L2 messages are pushed via the Inbox contract on L1. Whenever a message is sent, it's accumulated into a tree. This tree is then `consume`d by a checkpoint `propose`d in the Rollup contract, and a new tree is opened.

After pipelined block building was implemented, a 2-checkpoint lag was introduced on the Inbox. This guarantees that the messages to be consumed by a checkpoint are frozen by the time the build frame of that checkpoint starts. To illustrate:

| Time  | Slot | Event                                                                                                   |
| ----- | ---- | ------------------------------------------------------------------------------------------------------- |
| -12s  | N-1  | Build frame for slot N+1 starts with checkpoint C+1.                                                    |
| ~36s  | N    | Checkpoint C for slot N is mined on L1. Inbox seals tree T+2 for checkpoint C+2 and opens tree T+3.     |
| 60s   | N    | Build frame for slot N+2 starts with checkpoint C+2 with messages from tree T+2.                        |
| ~108s | N+1  | Checkpoint C+1 for slot N+1 is mined on L1. Inbox seals tree T+3 for checkpoint C+3 and opens tree T+4. |
| 132s  | N+1  | Build frame for slot N+3 starts with checkpoint C+3 with messages from tree T+3.                        |
| 138s  | N+1  | First block from checkpoint C+3 adds all messages to world state and gets broadcasted by its proposer.  |
| 144s  | N+1  | That first block is validated and added by nodes in the network.                                        |

Tree T+3 is opened when checkpoint C landed on L1, and sealed when checkpoint C+1 landed. It is fed into checkpoint C+3. This means that messages sent between the ~36s and ~108s mark are injected in a block at the 132s mark, so it's available on the proposed chain between the 132-144s mark.

All in all, the latency between an L1-to-L2 message being mined on L1 and it being added to L2 world state is anywhere between **24s and 108s**.[^latency]

Note that all L1-to-L2 messages for a checkpoint are added at its start, before processing the first transaction of the first block in the checkpoint. Also note that, for a tx to make use of the message, it needs to reference a world state tree root that contains it, so consumers need to wait for that first block to be emitted.

### How are messages verified today

Checkpoints carry a world-state tree root and an `inHash` in their header. The `inHash` is a SHA256 commitment to the messages added at the beginning of the checkpoint, structured as a frontier tree, as assembled by the `Inbox` contract. When the checkpoint is mined on L1, its `inHash` is checked against the one on the `Inbox` (considering the lag). This verifies that the messages declared by the checkpoint correspond to the ones on the `Inbox`.

The other half of the work is checking that the messages inserted into world-state correspond to the `inHash` commitment. Here, a set of circuits verify that the messages correspond to both the SHA256 frontier tree commitment (the `inHash`) and a merkle poseidon subtree root. These circuits are dubbed the `parity` circuits, since they check the parity between both commitments. The subtree root is then inserted into the L1-to-L2 messages tree of world-state by the first block of the checkpoint.

## Specification

Rather than waiting for an Inbox tree to be sealed in order to inject all its messages simultaneously at the beginning of the next checkpoint to be built, we stream L1-to-L2 messages into the checkpoint as they are received by the Inbox. In other words, after the Inbox receives a message, that message is inserted into the next block being built by the current proposer, regardless of whether that block is the first on the checkpoint or not.

This couples the proposed chain more tightly to L1, so an L1 reorg could invalidate the last L2 blocks built which depended on the messages included. We propose adding a lag of `INBOX_LAG_SECONDS=12s` to guard against shallow reorgs, enforced by L2 nodes when validating block proposals rather than by L1. Alternatively, we could drop this lag, further reducing latency, at the cost of either building machinery to roll back the last few proposed blocks and re-build them, or aborting the entire slot.

The end result should be that a message is included in a new L2 block that starts being built 12-18s after it is mined on L1. Given the block becomes available no more than 12s later to users, the total latency now drops to between **12s and 30s**[^latency], down from the current 24-108s.

### Inbox redesign

The Inbox must now account for checkpoints that will consume messages up until near the end of their corresponding build frame. This means that message trees should not be closed based on when a checkpoint lands.

We propose that the Inbox now commits to the messages it has received exclusively via a rolling hash, which gets snapshotted into buckets _per L1 block_, along with the total number of messages, in a circular storage structure. This gives checkpoints the flexibility to define up to which L1 block they have consumed messages when they are posted to L1. Note that this rolling hash is not necessarily the truncated 128-bit one the Inbox keeps today for node syncing: as a consensus-critical commitment, it should likely use the full 256 bits.

The `Rollup.propose` call receives the checkpoint header, which includes the checkpoint's `inHash`, now redefined to be the last rolling hash of Inbox messages that were bundled into the checkpoint. The Rollup contract then checks that the proposed `inHash` matches a valid rolling hash from the Inbox.

This gives builders the flexibility to decide which messages are actually included in the checkpoint, giving them optionality on the `INBOX_LAG_SECONDS` to use.

#### Messages cap and overflowing

Circuits enforce a maximum number of messages to be inserted per checkpoint. Assuming we move that restriction to blocks, we can define a `MAX_L1_TO_L2_MSGS_PER_BLOCK=256`. The Inbox cannot accept more than that number of messages per L1 block, or that bucket would become impossible to consume by a checkpoint. A simple solution is to just revert on overflow, and have clients wait until the next L1 block to send a message.

A more user-friendly solution instead is to roll over the excess of messages onto the next bucket. `Inbox` would require a pointer to the current bucket for accumulating inbound messages, and choose the current bucket based on the max of that pointer and the current L1 block.

Note that circular storage introduces a hazard here: a bucket that has not yet been consumed could be overwritten once the ring wraps around, so an L2 outage longer than the ring covers would permanently destroy in-flight messages. The Inbox must either refuse inserts that would overwrite an unconsumed bucket, halting message sends for the remainder of the outage, or fall back to plain non-circular storage.

We lean towards the rollover solution: reverting on overflow makes message sending griefable, since anyone can cheaply fill a bucket to delay a victim's message, whereas rolling over keeps sends live and only delays consumption.

#### Preventing censorship

Given the proposer and the committee choose which is the last message bucket consumed in the checkpoint, based on the last block they produced on the checkpoint, the Rollup must ensure that the Inbox is emptied regularly. Otherwise, a malicious committee could choose to never consume any messages, censoring L1-to-L2 messages flowing into the Rollup.

We define the cutoff as the latest Inbox bucket at or before the start of the build frame of the proposed checkpoint. Every message in that bucket or an earlier one was visible for the entire build frame, so the committee had every opportunity to include it. Note that this also bounds the _maximum_ lag a proposer can apply to roughly one build frame, while `INBOX_LAG_SECONDS` sets the minimum.

However, the Rollup must not force the checkpoint to consume more than `MAX_L1_TO_L2_MSGS_PER_CHECKPOINT`. Since checkpoints consume whole buckets and each bucket snapshots the cumulative message count, the check becomes: the checkpoint is acceptable if consuming one more bucket would either go past the cutoff or overflow the cap.

```
contract Rollup
  def propose(checkpoint)
    bucket = inbox.storage[checkpoint.inHash]
    next = bucket.next  # first bucket not consumed by the checkpoint, if any
    assert next == none  # consumed everything in the Inbox
        or next.l1Block > cutoff(checkpoint.slot)  # or everything up to the cutoff
        or next.total > prev.total + MAX_L1_TO_L2_MSGS_PER_CHECKPOINT  # or as much as the cap allows
```

#### Possible optimizations

As an optimization, it may be possible to have the Inbox snapshot the messages per L2 slot instead of L1 block, and close the snapshot roughly `INBOX_LAG_SECONDS` before the end of the current build frame. However, it's unclear if this would reap any gas benefits, since the Inbox storage can be implemented as circular storage.

Note that this would _remove_ the optionality for proposers to choose exactly up to which `Inbox` bucket they consume, and would instead be mandated by the Rollup contract.

We recommend against this optimization, at least in a first iteration: it removes proposer optionality, couples the Inbox to L2 slot arithmetic, and the gas savings are unclear.

### Updated checkpoint and block headers

As mentioned, today checkpoint headers have the `inHash` of the sealed L1-to-L2 subtree they consume from the Inbox. These messages are all appended simultaneously before the first block.

In this new model, since each block includes new messages, each block requires a commitment to the messages inserted in it. The checkpoint's `inHash` is then the `inHash` of the _last_ block of the checkpoint, and the `inHash` is redefined to be the rolling SHA256 from the `Inbox`. The L1-to-L2 world state tree then mutates on each block, not just on the first block of each checkpoint.

When broadcasting a block proposal to the network, the proposer now includes an `inHash` for the block, which informs the nodes that receive the proposal which L1-to-L2 messages they need to pull from the `Inbox` and insert into the block before reexecuting it. The `inHash` chosen by the proposer should be validated by all nodes, and rejected if invalid, or is too old, or includes too many messages.

#### Acceptance conditions for proposed blocks

A node that receives a block proposal carrying an `inHash` performs the following checks on it:

1. **The `inHash` exists on the Inbox.** The node looks up the `inHash` in its own view of the Inbox, synced from L1. If unknown, the node waits for its L1 sync to catch up to the L1 head within its proposal validation deadline, and rejects the proposal otherwise.
2. **The `inHash` moves forward.** The bucket referenced by the proposal must be the same as or newer than the one referenced by the parent block. If it is the same, the block adds no messages.
3. **The `inHash` is not too new.** The bucket's L1 block must be at least `INBOX_LAG_SECONDS` old at validation time, so that a shallow L1 reorg cannot invalidate the block. This makes `INBOX_LAG_SECONDS` the minimum lag enforced by the network, complementing the maximum enforced by the censorship cutoff. This check could be dropped in favor of allowing proposers to unilaterally remove this lag at the risk of L1 reorgs invalidating their checkpoint.
4. **The message bundle is within caps.** The node derives the bundle itself as all Inbox messages after the parent block's bucket up to and including the proposed one, in insertion order, so the proposal does not need to carry the messages. The bundle must not exceed `MAX_L1_TO_L2_MSGS_PER_BLOCK`, and the running total for the checkpoint must not exceed `MAX_L1_TO_L2_MSGS_PER_CHECKPOINT`.

The node then inserts the bundle into its L1-to-L2 message tree, re-executes the block's txs, and checks the resulting state reference against the proposed block header before attesting. When attesting to the last block of a checkpoint, the node additionally verifies that the checkpoint satisfies the minimum consumption rule defined in the `Inbox` censorship section.

#### Empty blocks

Today circuits only allow an empty block to be the first block in the checkpoint. However, this means that a proposer cannot consume new L1-to-L2 messages to make them available to users if the tx pool is empty. We should allow a non-first block without txs in a checkpoint if it contains some L1-to-L2 messages.

#### Revisiting timestamps

Today blocks inherit the same timestamp as their checkpoint, which is the beginning of their target slot. We could let blocks have any timestamp within the slot, as long as the committee accepts it, and use that to reference an Inbox bucket. Note that this would require storing timestamps in the Inbox as well, and possibly additional checks in circuits. Whether this is a net benefit depends on what checks are enforced by L1 and circuits, which are detailed in the section below.

We suggest keeping timestamps as they are today and referencing Inbox buckets by L1 block number instead: per-block timestamps bring extra Inbox storage and circuit checks, and nothing in this proposal depends on them.

### Verification and circuits

In this new model, we now have bundles of L1-to-L2 messages added to each block within the checkpoint. We have different options on how strict we want to be in verifying these.

#### Option 1: Validate every block `inHash` matches an `Inbox` slot

When a checkpoint is published to L1, we also include the list of `inHash` values for each of its blocks. Each of these is verified against the `Inbox`. This ensures that every message bundle injected into a block corresponds to an existing message bundle in the `Inbox`. If we allow distinct timestamps per block, we could additionally check that those match the ones from the `Inbox` bucket they are consuming, accounting for the lag.

```
contract Rollup
  def propose(checkpoint)
    for block in checkpoint
      assert block.inHash in inbox.storage
```

Circuits then check that the `inHash` of each block follows from accumulating the block's messages on top of the previous block's `inHash`, that those messages are inserted into the L1-to-L2 message tree, and that the checkpoint's `inHash` is the same as the last block's.

```
circuit BlockRoot
  assert sha256(lastBlock.inHash, msgs) == block.inHash
  assert merkleInsert(lastBlock.stateref.l1ToL2, msgs) == block.stateref.l1ToL2.root

circuit CheckpointRoot
  assert blocks[-1].inHash == checkpoint.inHash
  assert blocks[-1].stateref == checkpoint.stateref
```

This option is particularly expensive in terms of L1 gas, since it requires one `SLOAD` per block in the checkpoint. As for the parity checks, it's unclear whether they would be moved to the BlockRoot circuit, or kept as a separate set of circuits as they are today.

#### Option 2: Validate checkpoint `inHash` on L1 and block `inHash` in circuits

When a checkpoint is published to L1, we verify that its `inHash` matches a recent one from the Inbox, rather than verifying each individual block's.

```
contract Rollup
  def propose(checkpoint)
    assert checkpoint.inHash in inbox.storage
```

Circuits run the same checks as in the previous option.

```
circuit BlockRoot
  assert sha256(lastBlock.inHash, msgs) == block.inHash
  assert merkleInsert(lastBlock.stateref.l1ToL2, msgs) == block.stateref.l1ToL2.root

circuit CheckpointRoot
  assert blocks[-1].inHash == checkpoint.inHash
  assert blocks[-1].stateref == checkpoint.stateref
```

This option is cheaper in terms of L1 gas, roughly same as it is today, since it requires only one `SLOAD` from the `Inbox` per checkpoint. It does **not** guarantee that the messages added in each block map to slots in the `Inbox`. A proposer could split the checkpoint messages across its blocks however it sees fit, though all messages until the last one consumed must be included and in order for the rolling hash to match. Nevertheless, the committee could restrict that messages are bundled and consumed based on how they were inserted in the `Inbox`.

#### Option 3: Validate only checkpoint `inHash` on both L1 and circuits

The rollup check is the same as in option 2.

```
contract Rollup
  def propose(checkpoint)
    assert checkpoint.inHash in inbox.storage
```

Circuits only check that the _checkpoint's_ `inHash` is the commitment of all L1-to-L2 messages added throughout the checkpoint. This means that circuits would not catch the `inHash` in a block header not matching the messages inserted in that block. Nevertheless, since the `inHash` is still checked at the checkpoint, circuits guarantee that the correct list of messages is inserted across blocks. A sponge is used to verify that the list of messages passed into the `CheckpointRoot` circuit is the same as the messages inserted into each of the `BlockRoot` circuits.

```
circuit BlockRoot
  assert merkleInsert(lastBlock.stateref.l1ToL2, msgs) == block.stateref.l1ToL2.root
  block.inHashSponge = lastBlock.inHashSponge.absorb(msgs);


circuit CheckpointRoot
  assert sha256(lastCheckpoint.inHash, blocks.msgs) == checkpoint.inHash
  assert blocks[-1].inHash == checkpoint.inHash
  assert blocks[-1].stateref == checkpoint.stateref
  assert blocks[-1].inHashSponge == lastCheckpoint.inHashSponge.absorb(blocks.msgs)

```

This option is simpler in terms of changes to circuits, since the parity circuit today predicates over the L1-to-L2 messages of the entire checkpoint, not of each block. However, it means that it's possible to prove the validity of a checkpoint that contains blocks whose headers' `inHash` values do not correspond to the messages they include. A workaround to this could be to just _remove_ the `inHash` from block headers, and only use them in block proposals to signal the messages to be included. Again, the correctness of `inHash`es would still be enforced by the committee and the L2 network itself.

We suggest going with this option, along with removing the `inHash` from block headers. The extra guarantees of options 1 and 2 only protect the integrity of a header field: in all three options, which messages are inserted into world-state, and in what order, is equally constrained. If the field is not part of the header, there is nothing to lie about, and the soundness concern described in the security considerations below evaporates. Nodes still validate each block's message bundle at proposal time, which is where it actually matters.

## Rationale

The core design decision is to stream L1-to-L2 messages into blocks as they are received by the Inbox rather than batching them per checkpoint, trading a tighter coupling to L1 for lower message latency. The `INBOX_LAG_SECONDS` lag exists to guard against shallow L1 reorgs invalidating recently built blocks. The rationale for the remaining design decisions — rolling over messages on overflow, the censorship cutoff, keeping timestamps as they are today, and the choice among the three verification options — is discussed inline in the Specification above.

## Backwards Compatibility

This proposal changes the L1 `Inbox` and `Rollup` contracts, the rollup circuits, and the L2 consensus rules, as detailed in the Specification and Appendix. It removes the `AZTEC_INBOX_LAG` constant and introduces `INBOX_LAG_SECONDS`, `MAX_L1_TO_L2_MSGS_PER_BLOCK`, and `MAX_L1_TO_L2_MSGS_PER_CHECKPOINT`.

## Security Considerations

### Consuming messages before they are inserted into the `Inbox`

Circuits and L1 no longer enforce that messages are actually present in the `Inbox` before they are inserted into the L2 world-state and can be consumed. Assuming a malicious committee, the proposer for a slot can first add a bundle of messages to an L2 block corresponding to a not-yet-existing `inHash`, then push the messages to the Inbox to produce said `inHash` after-the-fact, and eventually have it confirmed by the checkpoint and circuits. This is possible because L1 only syncs with L2 during checkpoints, so the ordering of events within a checkpoint with respect to L1 can only be enforced by the L2 network itself.

We believe this is not an issue. Nodes in the network validate `proposed` blocks before accepting them, so this behavior should be rejected by the network while the checkpoint is being built. This means that no honest party following the L2 proposed chain would act on these L1-to-L2 messages before they are actually present on L1. And since L2-to-L1 messages are not delivered to the Outbox at least until the checkpoint is mined, there is also no risk of tricking L1 itself by creating a spurious exit from a not-yet-existing inbound message.

These blocks would eventually be accepted by the network once they are `checkpointed` on L1, but by that time, the malicious committee must have actually inserted the messages into the `Inbox` for the checkpoint's `inHash` to match.

### Soundness issues in circuits

Verification options 2 and 3 above mean that a malicious committee can checkpoint blocks that are not valid from the perspective of the rest of the network, but circuits and L1 would still accept them. In most scenarios, the extent of the damage a malicious committee can produce goes as far as the checkpointed chain, since rollup circuits would catch any validity issues. However, in this scenario we have an invalid chain that is provable.

We think this is acceptable, by virtue of relaxing what we consider to be valid on the proposed vs the checkpointed chain. A proposed block is valid if it references a valid `inHash` from the `Inbox` at the time it is received. A checkpointed block is valid if its checkpoint's `inHash` references a valid `inHash`, which is checked by L1, and the checkpoint's L1-to-L2 messages are added throughout its blocks in the correct order.

This means that nodes would reject a proposed chain where messages are not properly pulled from the `Inbox`, but if the total list of messages added in the checkpoint is valid, nodes would accept them, which matches the checks enforced by circuits.

## Appendix

### Constants

| Constant                           | Suggested value   | Scope                         | Notes                                                                                                                                          |
| ---------------------------------- | ----------------- | ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `INBOX_LAG_SECONDS`                | 12s (one L1 slot) | L2 consensus, proposer policy | New. Minimum age of an Inbox bucket for nodes to accept it in a block proposal; proposers may apply a larger lag, up to the censorship cutoff. |
| `MAX_L1_TO_L2_MSGS_PER_BLOCK`      | 256               | L1, circuits, L2 consensus    | New. Cap on messages per Inbox bucket and per L2 block.                                                                                        |
| `MAX_L1_TO_L2_MSGS_PER_CHECKPOINT` | 1024              | L1, circuits, L2 consensus    | Today's `NUMBER_OF_L1_L2_MESSAGES_PER_ROLLUP`. Caps messages per checkpoint and bounds the mandatory consumption on propose.                   |
| `AZTEC_INBOX_LAG`                  | —                 | L1                            | Removed. Today's 2-checkpoint lag on the Inbox, replaced by `INBOX_LAG_SECONDS`.                                                               |

## Copyright Waiver

Copyright and related rights waived via [CC0](/LICENSE).

[^latency]: Latency ranges take the best case for the lower bound and the worst case for the upper bound. If blocks are small enough and propagation is fast enough, building and validating a block takes near-zero time, so a message becomes available to the network almost as soon as the block that includes it starts being built. The upper bound instead allows roughly 12s from build start to network-wide availability.
