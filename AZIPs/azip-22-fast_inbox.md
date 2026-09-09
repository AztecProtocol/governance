# AZIP-22: Fast Inbox

## Preamble

| `azip` | `title`    | `description`                                                                                                                         | `author`                                                  | `discussions-to`                                           | `status` | `category` | `created`  |
| ------ | ---------- | ------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------- | ---------------------------------------------------------- | -------- | ---------- | ---------- |
| 22     | Fast Inbox | Streams L1-to-L2 messages into blocks as they arrive on the Inbox rather than batching them per checkpoint, reducing message latency. | Santiago Palladino (@spalladino, santiago@aztec-labs.com) | https://github.com/AztecProtocol/governance/discussions/53 | Draft    | Core       | 2026-07-01 |

## Abstract

This proposal streams L1-to-L2 messages into blocks as soon as nodes observe them on L1, removing the two-checkpoint
Inbox lag. A rolling hash commits to the ordered message sequence. Blocks may consume arbitrary prefixes of that
sequence, while checkpoints must end at an L1 Inbox bucket boundary. Nodes check that boundary when receiving a
checkpoint proposal, and the Rollup enforces consumption limits and censorship protection at publication.

## Impacted Stakeholders

Users and applications gain earlier access to inbound messages. Sequencers select messages throughout checkpoint
building; nodes, including validators, authenticate those messages and the final checkpoint boundary. Provers verify
compact per-block insertion. Portal sends are subject to backpressure when the Inbox ring fills.

## Motivation

The existing Inbox seals message trees when checkpoints land on L1 and introduces a two-checkpoint delay before those
messages enter L2 world state. All messages for a checkpoint are inserted before its first block, so later blocks cannot
use newly arrived messages.

Decoupling message insertion from checkpoint boundaries removes this fixed wait. Availability on the proposed chain
then depends on L1 synchronization, block building and propagation, subject to backlog and capacity. There is no minimum
message age or confirmation-depth requirement, and no fixed latency guarantee.

## Specification

### Inbox commitment and buckets

Starting from zero, the Inbox extends a rolling hash for each message leaf:

```
hash' = sha256ToField(DOM_SEP__INBOX_ROLLING_HASH ‖ hash ‖ leaf)
```

The domain separator is the four-byte big-endian value `3737216265`; the hash and leaf are each 32-byte big-endian
values. `sha256ToField` drops the last byte of the SHA256 digest and prepends a zero byte. Each link therefore hashes
68 bytes. The chain commits only to message contents and order: no timestamps, bucket separators or block markers
enter it.

The Inbox snapshots the chain into buckets containing `{rollingHash, totalMsgCount, timestamp, msgCount}`, packed into
two storage slots. A new bucket opens on the first message of a new L1 block or when the preceding bucket is full.
Each bucket holds at most 256 messages; additional messages roll into another bucket, including within the same L1
block. Bucket zero is an empty genesis sentinel with hash and counts zero.

Buckets have dense sequence numbers and occupy a fixed ring at `seq % ringSize`. Reads reject entries outside the live
window. The production ring has 4096 entries, with a constructor minimum of 512.
`getBucketAtOrBeforeTotal(upperBound)` returns the live bucket with the greatest cumulative count at or below the bound,
or fails if none exists.

Message indices are compact and zero-based: a message's index is the total number of messages preceding it. Blocks
append their messages at the current tree offset without padding. `sendL2Message` returns the index, and `MessageSent`
emits the full message including that index.

### Checkpoint publication and censorship protection

The checkpoint header replaces `inHash` with `inboxRollingHash`, the rolling hash after its final consumed message.
`Rollup.propose` takes an unsigned `bucketHint` identifying the corresponding live bucket. The hint is a lookup aid;
the header hash is the commitment.

For a checkpoint in slot `S`, define:

```
buildFrameStart(S) = toTimestamp(S - 1)
cutoff(S)          = buildFrameStart(S) - ethereumSlotDuration
```

The offset uses the configured L1 slot duration, normally 12 seconds. It defines mandatory consumption, not a minimum
age for consuming a message.

Against the effective parent checkpoint after any automatic prune, the Rollup requires:

1. The referenced live bucket's rolling hash equals the checkpoint header's `inboxRollingHash`.
2. The bucket is settled: it is the genesis sentinel, was opened before the executing L1 block's timestamp, or is full.
3. Its cumulative count is at least the parent's consumed count and at most 1024 messages ahead.
4. The next bucket either does not exist, opened strictly after the cutoff, or would take consumption beyond the
   1024-message checkpoint cap.

A bucket opened exactly at the cutoff is mandatory unless the cap escape applies. A checkpoint consuming no messages
keeps its parent's count and hash and remains subject to the same rules.

The Rollup records the consumed hash, cumulative count and bucket sequence for each checkpoint. These records follow
the pending chain through prunes and provide the anchors for proof verification and ring eviction.

`validateCheckpointHeaderAndInbox` provides the proposer with a shared header-and-Inbox preflight. It checks the
expected parent against the effective parent in the simulated Rollup context, resolves the expected message total to
an exact bucket endpoint, applies the same Inbox consumption checks as `propose`, and returns the bucket hint.
The proposer runs it before gossiping the checkpoint and again before publication, accounting for a pipelined parent
or a preceding invalidation as applicable. Simulation does not guarantee later transaction acceptance.

### Block and checkpoint validation

Every block proposal carries a signed `InboxMessagePrefixRef` containing its ending rolling hash. The ending count
comes from the block header's L1-to-L2 tree `nextAvailableLeafIndex`, so the signature binds both count and hash.
There is no separate Inbox commitment in the block header.

For each proposed block, nodes require forward-only consumption, at most 256 new messages, and at most 1024 messages
across its checkpoint. They read the exact range `[parentCount, endCount)` and its endpoint hashes from one consistent
local message-store snapshot, authenticate the signed prefix, insert the messages, re-execute transactions and check
the resulting state against the header. Block insertion rechecks the prefix and parent atomically with the store write
to prevent a concurrent message rewind from admitting stale work.

An intermediate block may end inside an L1 bucket. Nodes impose no message-age check. An unavailable or mismatching
local prefix prompts bounded synchronization and retry; inability to confirm it is not evidence of proposer misconduct
and must not trigger slashing or peer penalties. The same applies to a state mismatch caused by the local prefix
changing during validation.

When a checkpoint proposal arrives, all receiving nodes, including validators, must additionally:

- Authenticate its full consumed message range and require its ending hash to match both the checkpoint header and
  the last block's signed prefix.
- Resolve the final cumulative count against the live L1 Inbox and require an exact bucket boundary with the same
  rolling hash. A matching arbitrary prefix alone is insufficient.
- Reconstruct the checkpoint from its validated blocks and enforce the block-count cap.

A checkpoint whose endpoint cannot be confirmed is not accepted or attested while that check is unresolved.
Temporary L1 unavailability or conflicting local views must not be treated as proof of proposer misconduct.
This boundary check does not replace the proposer's full publication preflight or the Rollup's settlement and
censorship checks.

### Proposer selection and completion

Ordinary blocks greedily consume locally observed messages up to the per-block and per-checkpoint caps. The proposer
checks that each range starts at the prefix its preceding blocks consumed; a changed prefix aborts the checkpoint.

To leave room for a valid final boundary, the proposer queries a live endpoint whenever the next greedy block would
end strictly beyond `checkpointStart + 768`, and on every final block. The threshold reserves one maximum-sized bucket
within the 1024-message checkpoint cap.

For a non-final block, the lookup is bounded by the local message count and checkpoint cap; the block takes up to
256 messages toward that endpoint and may still end inside a bucket. It never consumes less than the safe local step
ending at or below the threshold. If resolution fails, that safe step remains available. Selection is repeated from
the current view for each block, without retaining or freezing a target.

For the final block, the lookup is also bounded by that block's remaining reach. It must return a content-matching
endpoint at or beyond the current cursor; otherwise the checkpoint is abandoned. If the normal sub-slot schedule
ends inside a bucket, the proposer attempts one extra transaction-less completion block under the final build-time
budget and the same caps. The checkpoint still has to pass the publication preflight. Already signed blocks are not
rewritten, and a second checkpoint is not signed for the same duty.

Checkpoints contain at most 72 blocks. Fully empty blocks are legal at any position, and message insertion does not
require transactions. A network's configured maximum blocks per checkpoint must lie between 4 and 72; four blocks
provide capacity for the 1024-message cap.

Public functions may consume messages inserted by their own block, because insertion precedes transaction execution.
Private consumption still requires membership against a historical header available to the wallet. Blocks retain
their checkpoint's timestamp.

### Node storage and reorg recovery

Nodes store the ordered message log with compact indices, leaves, cumulative hashes and L1 synchronization metadata.
They do not persist the bucket partition. Live boundary checks query L1; published-block replay reads exact count
ranges from block headers and does not depend on historical bucket boundaries. Missing ranges are errors, never
silently empty bundles.

Synchronization checks the local count and hash against an observed L1 head. On disagreement, recovery finds a matching
message prefix and replays canonical events in bounded batches. Replacements are compared by content. Suffix replacement,
syncpoint updates and pruning of affected proposed blocks are atomic. Recovery does not advertise an agreeing head
until synchronization reaches it, and speculative work is withheld when the checkpointed tip disagrees with the log.
Published-chain changes remain the checkpoint synchronizer's responsibility.

Re-mining the same messages with different timestamps or bucket partitions leaves their prefix hashes unchanged and
does not invalidate intermediate blocks. Changed or removed messages invalidate the proposed chain from the first block
that consumed them. A completed checkpoint can nevertheless lose its final bucket boundary even when all messages
survive, making that checkpoint unpublishable.

### Verification and circuits

One `InboxParity<S>` proof per checkpoint replaces the frontier-tree parity family. The prover selects the smallest
size in `{64, 256, 1024}` that fits the message count. The circuit requires zero padding beyond the real messages,
extends a witnessed starting rolling hash over the real leaves, and absorbs those same leaves into an initially empty
Poseidon2 message sponge. Padding enters neither accumulator.

Each block-root circuit proves the compact message-tree append and absorbs its actual bundle into the checkpoint's
running message sponge. The checkpoint root equates the complete ending sponge with the parity proof's sponge,
including its cached state and absorbed count. No bucket or block separators enter either message accumulator.

Checkpoint merges require rolling-hash continuity. L1 anchors the start of a proven range to the preceding checkpoint's
stored hash; the end is bound through the final checkpoint header. Both ends are necessary to prevent replaying an
already-consumed suffix. The start is derived from the parent and is not an additional header field.

The checkpoint root also enforces the block cap and initial message/blob sponge states, connects the starting state
to the previous archived block header, and enforces timestamp progression across checkpoints. Block merges carry
state and sponge continuity through the checkpoint. Block-root variants are position-independent.

Although the proposer chooses the per-block split, the prover cannot change an attested split: each block header
commits to its post-insertion message-tree snapshot, the archive commits to those headers, and the proof is checked
against the attested archive roots stored on L1. Blob data includes the L1-to-L2 message-tree root for every block.

### Ring backpressure

The Inbox rejects sends that would overwrite an unconsumed bucket. Eviction advances with proven consumption, using
the checkpoint's recorded bucket sequence when its epoch proof is accepted. Pending checkpoints cannot free space
that a prune might require again.

This prevents silent loss through ring overwrite, but a prolonged proving stall or sustained message spam can halt
sends through every portal until proven consumption frees space. The ring supplies finite headroom; the censorship
cap escape does not throttle L1 arrivals. `getRingHeadroom` exposes the available capacity.

## Rationale

The rolling hash separates message arrival from checkpoint publication while keeping L1 checks independent of the
number of L2 blocks. Compact indices and arbitrary block prefixes allow continuous insertion without padding or a
persisted bucket layout. Bucket endpoints provide bounded L1 snapshots for publication and censorship enforcement.

Immediate consumption accepts reorg exposure in exchange for lower latency. Committing only to message contents and
order preserves proposed blocks when L1 re-mines unchanged messages. Nodes check the final checkpoint boundary before
acceptance, while L1 remains authoritative for publication.

## Backwards Compatibility

This is a coordinated change to L1 contracts, rollup circuits, proposal validation and blob encoding, deployed in a new
rollup instance. There is no migration of in-flight messages; messages in the old Inbox remain attached to the old
instance.

The main interface changes are:

- Checkpoint `inHash` becomes `inboxRollingHash`; `propose` gains the unsigned bucket hint, and epoch proofs carry
  rolling-hash range anchors.
- Block proposals carry signed message-prefix references. Checkpoint recipients check the final L1 bucket boundary.
- Message indices become compact; `MessageSent` emits the full message, and `getL1ToL2MessageCheckpoint` is replaced
  by `getL1ToL2MessageIndex`.
- Archiver bucket APIs are replaced by count-addressed position/range reads; the message-store schema change requires
  resynchronization.
- Blob encoding carries a message-tree root for every block. The two-checkpoint Inbox lag is removed.

## Security Considerations

The rolling hash and parity/message-sponge checks bind the exact ordered message list; the attested block headers bind
its insertion into individual blocks. Domain separation distinguishes Inbox links from other SHA256 constructions.
L1's settled-bucket check prevents publication against a mutable same-execution snapshot.

Circuits do not prove when a message first appeared on L1 relative to a proposed block. Honest nodes enforce presence
through their own message view and check the checkpoint endpoint on receipt. A non-cooperative committee could build
with messages inserted on L1 only later, but publication and proof verification still require the final anchored list.

The following limitations remain:

- A reorg can remove a completed checkpoint's final boundary, costing the checkpoint even if its messages survive.
- A passing node boundary check or proposer preflight is a check of an observed state. It neither proves future
  publishability nor replaces L1's full acceptance rules. A later reorg can revert `propose` and spend L1 gas.
- Recovery retains an inherited finalized-height shortcut. A message re-mined higher with unchanged content can retain
  its old recorded height and later be trusted as finalized prematurely, without any finalized Ethereum block being
  reverted. Repairing this shortcut is deferred.
- Recovery needs an L1 provider that can serve canonical message history back to its anchor, potentially the Inbox
  deployment block. Provider failures must not be interpreted as absence of messages.
- Ring exhaustion halts new sends until proving frees space; finite capacity cannot absorb indefinite overload.

## Constants

| Parameter | Value |
| --- | --- |
| Messages per block / per Inbox bucket | 256 |
| Messages per checkpoint | 1024 |
| Maximum blocks per checkpoint | 72 |
| Minimum configured blocks per checkpoint | 4 |
| Production bucket ring / constructor minimum | 4096 / 512 |
| Endpoint lookup threshold | Checkpoint starting count + 768 |
| Inbox rolling-hash domain separator | 3737216265 |
| Parity circuit sizes | 64 / 256 / 1024 |
| Censorship cutoff offset | Configured `ethereumSlotDuration` |
| Minimum consumption lag | None |

## Copyright Waiver

Copyright and related rights waived via [CC0](/LICENSE).
