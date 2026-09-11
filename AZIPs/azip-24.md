# AZIP-24: Track First Prover Attribution for Checkpoints

## Preamble

| `azip` | `title`                                        | `description`                                                                                                       | `author`                                                  | `discussions-to` | `status` | `category` | `created`  |
| ------ | ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------- | ---------------- | -------- | ---------- | ---------- |
| 24     | Track First Prover Attribution for Checkpoints | Makes the first prover of every proven checkpoint queryable, enabling applications to reward early message release. | Santiago Palladino (@spalladino, santiago@aztec-labs.com) | N/A              | Approved    | Core       | 2026-09-04 |

## Abstract

This AZIP adds a queryable record of the prover that first advanced the proven tip over each checkpoint. The Rollup stores one sparse attribution entry at the end of each proof range that advances the tip. `getFirstProvenBy(checkpointNumber)` resolves any proven checkpoint to the prover whose proof first covered it. This lets a sender or application pay an out-of-protocol tip to the prover responsible for making an L2-to-L1 message available in the outbox, including when that availability comes from a proof of only part of an epoch. It does not add protocol rewards or change proof validity, message processing, or the existing reward distribution.

## Impacted Stakeholders

**Message senders and applications.** A sender or application that benefits from an L2-to-L1 message becoming executable sooner can query a canonical prover address after the checkpoint is proven. It can use that result in its own escrow or settlement scheme to pay a fast-exit tip. The protocol neither escrows the tip nor enforces its payment.

**Provers.** A prover that first submits a valid proof advancing coverage over a checkpoint gains a stable, on-chain attribution for that checkpoint. This makes application-level compensation possible for partial-epoch proofs, which currently receive no additional protocol reward merely for releasing messages early. A prover that proves an already-covered range gains no attribution because it does not advance the proven tip.

**Bridges and other L2-to-L1 message consumers.** These applications may use the getter to settle incentives tied to message release. They must continue to apply their existing validity and finality checks; prover attribution is not a substitute for verifying the message or proving its inclusion.

**Indexers and RPC providers.** They should expose the new `IRollup.getFirstProvenBy` read method if they expose the Rollup interface. They may use the sparse mapping semantics to derive attribution without reconstructing proof history from events.

**Sequencers and validators.** Their roles, rewards, and consensus rules do not change. The successful proof-submission path incurs one additional storage write when it advances the proven tip.

## Motivation

Aztec can accept a proof covering only part of an epoch. When such a proof advances the proven tip, it can push an L2-to-L1 message in a covered checkpoint to the outbox without waiting for the entire epoch to be proven. This permits fast exits and other latency-sensitive cross-domain actions.

The protocol does not currently reward a partial-epoch proof differently from an ordinary proof. The party that wants early message release is best placed to supply that incentive: a message sender, bridge, or related application can offer a tip and pay it out of band to the prover that released the message. However, the Rollup has no queryable, canonical record of which prover first proved a particular checkpoint. The existing proof event includes a prover identifier, but applications would need to independently index and interpret the proof history, while protocol reward accounting is organized around proof submissions rather than individual checkpoints.

Without a canonical attribution lookup, an application cannot safely and simply determine who earned a fast-exit tip. This AZIP supplies that lookup only. It deliberately leaves the amount, funding, eligibility rules, and settlement mechanism for incentives to the sender or application.

## Specification

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119 and RFC 8174.

### Definitions

- A **checkpoint** is the numbered Rollup unit that may contain L2-to-L1 messages.
- The **proven tip** is the highest checkpoint covered by an accepted epoch-root proof.
- A proof **advances the proven tip** when its ending checkpoint is greater than the tip before the proof is processed.
- The **first prover** of checkpoint `c` is the `proverId` carried by the earliest successful proof that advanced the proven tip to a value at least `c`. It is the proof's prover identifier, not necessarily the address that submits the L1 transaction.

### Attribution recording

The Rollup state MUST contain a mapping from checkpoint number to an encoded prover identifier.

When `submitEpochRootProof` accepts a proof whose ending checkpoint is greater than the current proven tip, it MUST:

1. Advance the proven tip as it does today.
2. Store the proof's `proverId` at the proof's ending checkpoint.

No attribution entry MUST be written for a proof that does not advance the proven tip. In particular, submitting a proof for an already-proven range MUST NOT replace the attribution produced by the proof that first covered that range.

Only the proof's ending checkpoint is stored. For example, a proof covering checkpoints 1 through 10 followed by a proof covering 11 through 20 produces entries at 10 and 20, and no entries at the intervening checkpoint numbers.

The stored representation MUST distinguish an intentionally recorded `address(0)` from an unwritten mapping entry. An implementation MAY store the address in the low 160 bits of a word and set bit 160 as a presence flag.

### Query interface

`IRollup` MUST expose:

```
function getFirstProvenBy(uint256 checkpointNumber) external view returns (address);
```

For a requested checkpoint `c`, the method MUST:

1. Revert with `Rollup__CheckpointNotProven(proven, c)` if `c` is zero or greater than the current proven tip `proven`.
2. Search forward from `c` until it finds the first attribution entry.
3. Return the prover identifier encoded by that entry as an address.

The returned entry is the earliest proof that covered `c`: the proven tip only moves forward, and each proof that advances it records an entry at its end. A valid proof covers at most one epoch, so a lookup finds its entry within at most the epoch duration in checkpoints. The implementation MAY revert with `Rollup__CheckpointNotProven(proven, c)` after the search only as an invariant failure; for every valid, nonzero proven checkpoint, an entry MUST exist at or after the requested checkpoint.

### No reward change

This AZIP MUST NOT change proof verification, the conditions under which the proven tip advances, L2-to-L1 message processing, fee allocation, block rewards, or prover rewards. It provides attribution for use by external incentive arrangements only.

## Rationale

### Attribute the first proof that releases the checkpoint

A fast-exit incentive is intended to reward the act that makes a message executable sooner. The first proof that advances coverage over the checkpoint performs that act. Later proofs may prove overlapping ranges but cannot make the checkpoint newly proven, so crediting them would reward work that did not release the message.

The `proverId` is used rather than `msg.sender` because it is the identifier already associated with the proof and its existing proof event. A proof submitter can be a relayer or another party distinct from the prover. Using the same identifier avoids creating two incompatible notions of who proved a checkpoint.

### Sparse entries with forward lookup

Writing an entry for every checkpoint in a proof range would make a partial proof more expensive in proportion to its length. The proposal instead writes one entry per proof that advances the tip. A lookup walks only to the end of the proof that first covered the checkpoint. Since a proof spans no more than one epoch, its work is bounded by the epoch duration.

### Alternatives considered

**Event-only attribution.** The existing proof event contains a prover identifier. Rejected because a sender or application would have to trust an indexer or implement its own event-history interpretation before it could settle a tip. A Rollup getter gives contracts and off-chain clients one canonical result.

**Store an entry for every checkpoint.** Rejected because it adds one storage write per checkpoint covered by a proof. It is unnecessary: proof ranges are contiguous and the monotonically advancing proven tip lets one endpoint entry identify every checkpoint in the range.

**Attribute the L1 transaction sender.** Rejected because a proof may be submitted by a relayer. The prover identifier is the relevant party for an incentive intended to reward proving.

**Add a protocol-level partial-proof reward.** Rejected because applications, not the protocol, know the value and conditions of fast message release. Out-of-protocol tips let each sender or application set those terms without modifying the global reward mechanism.

## Backwards Compatibility

This AZIP changes the Rollup contract state layout and interface, so it requires deployment of Rollup code containing the new getter and storage mapping through the applicable protocol upgrade process. It does not change L2 transaction encoding, proof validity, message semantics, or existing fee and reward rules.

Attribution is available only for proofs accepted by the upgraded Rollup. The new mapping does not backfill checkpoints proven before activation. Applications that support both deployments MUST treat pre-upgrade checkpoints as having no queryable first-prover attribution.

## Test Cases

1. Querying an unproven checkpoint reverts with `Rollup__CheckpointNotProven`, including when no checkpoints have been proven.
2. A proof of checkpoint 1 by Alice records Alice. A later proof of checkpoint 1 by Bob does not alter the result.
3. A proof of checkpoints 1 through 2 by Alice records one entry at 2; queries for both 1 and 2 return Alice.
4. After Alice proves checkpoint 1 and Bob proves checkpoint 2, querying 1 returns Alice and querying 2 returns Bob.
5. Querying checkpoint zero and any checkpoint above the proven tip reverts with `Rollup__CheckpointNotProven`.
6. A proof whose `proverId` is `address(0)` is recorded and returned as `address(0)`, rather than being treated as an absent sparse entry.
7. For arbitrary valid sequences of contiguous, tip-advancing proofs, every proven checkpoint resolves to the prover identifier of the first proof range that covered it, and each lookup completes within the epoch duration.

## Security Considerations

The attribution mapping does not validate a message, prove its inclusion, or determine whether an exit is executable. Applications using it for a tip MUST independently preserve their existing checks for the relevant outbox message and its settlement conditions.

The recorded value MUST be the `proverId` from the same successful proof submission that advances the proven tip. Recording `msg.sender`, accepting an identifier from a later transaction, or allowing later overlapping proofs to overwrite the entry could direct application-level incentives to a relayer or a non-releasing prover.

Sparse entries introduce a bounded read loop. The epoch-duration bound is security-relevant: implementations MUST retain the rule that a single proof cannot span more than one epoch. The presence flag prevents a valid zero-address prover identifier from being confused with missing state and avoids an unexpected revert or scan past its entry.

An application-funded tip is outside protocol accounting. Its escrow or payout contract SHOULD query the Rollup directly, specify the checkpoint it rewards, and make a single, replay-safe payout. It MUST NOT treat attribution as an authorization to withdraw unrelated funds.

## Copyright Waiver

Copyright and related rights waived via [CC0](/LICENSE).
