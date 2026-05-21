# AZIP-14: Multiple Roots per Epoch in the Outbox

## Preamble

| `azip` | `title`                                | `description`                                                                                                          | `author`                                                  | `discussions-to` | `status` | `category` | `created`  |
| ------ | -------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------- | ---------------- | -------- | ---------- | ---------- |
| 14     | Multiple Roots per Epoch in the Outbox | Lets the Outbox store multiple L2-to-L1 message roots per epoch so partial proofs do not invalidate pending user exits | Santiago Palladino (@spalladino, santiago@aztec-labs.com) | -                | Draft    | Core       | 2026-05-20 |

## Abstract

This AZIP modifies the L1 `Outbox` contract so that each epoch can accumulate multiple L2-to-L1 message roots rather than overwriting a single root every time a partial epoch proof is submitted. The nullifier bitmap that tracks consumed messages remains a single bitmap per epoch and is shared across all roots of that epoch. This eliminates a race condition in which a user's L1 exit transaction, built against a partial-proof root, reverts because a later proof for the same epoch has overwritten that root before the user's transaction is mined.

## Impacted Stakeholders

### App Developers and Token Bridges

Contracts that consume L2-to-L1 messages via `Outbox.consume` (including token bridges and any other L1 messaging bridge) MUST be updated to pass a new `rootIndex` parameter identifying which root of the epoch a given message was inserted against. Existing bridge UIs and SDKs that surface "claim on L1" flows MUST be updated to thread this index through.

### Wallets and PXE Implementers

Wallets and PXEs that build the calldata for an L1 exit (e.g. token withdraw claims) MUST resolve and include the `rootIndex` corresponding to the proof that included the user's message. Where the PXE today only needs to know "the root for epoch E", it now needs to know "the root for `(epoch E, rootIndex i)`".

### Infrastructure Providers (Indexers, Block Explorers, RPCs)

Off-chain decoders MUST handle the widened `RootAdded` event, which now carries a `rootIndex`. Indexers that map message hashes to epoch roots SHOULD index by `(epoch, rootIndex)`. Explorers SHOULD surface the root index alongside the epoch when displaying L2-to-L1 messages.

### Sequencers and Provers

No protocol-level changes are required to sequencing or proving. Provers that submit partial epoch proofs benefit from being able to chain additional proofs for the same epoch without invalidating outbox state observed by users. The additional compute effort to submit a partial epoch proof while the full proof is being constructed is under 1% (assuming 1 tx per second).

## Motivation

The current `Outbox` stores exactly one root per epoch and overwrites it on every `insert` call:

```solidity
mapping(Epoch => RootData) internal roots;
roots[_epoch].root = _root;
```

The protocol allows partial epoch proofs so that users can exit funds without waiting for a full epoch proof. The expected user flow is:

1. A user sends an L2 transaction containing an L2-to-L1 message (e.g. an exit).
2. A partial epoch proof covering that transaction lands on L1, populating `roots[epoch].root` with a root `R0` that includes the user's message.
3. The user submits an L1 transaction to `consume` the message, verifying inclusion against `R0`.
4. The user's L1 transaction is mined and successfully consumes the message.

However, the following could happen instead of the last step:

4. Before the user's L1 transaction is mined, a second partial proof for the same epoch lands and overwrites `roots[epoch].root` with `R1`.
5. The user's L1 transaction reverts because the merkle proof it carries no longer matches the current root.

The user wastes gas, sees a failed transaction, and must rebuild the claim against the new root and try again. Because L1 block times are short relative to the expected interval between successive partial proofs, the absolute frequency of this race is low — but for users who specifically opted into partial proofs to exit quickly, encountering it is a direct regression of the feature they paid for.

The existing protocol specification does not provide a way to preserve previously-submitted roots, so a user with a pre-built L1 exit cannot guarantee their transaction will succeed against any root they observed onchain. This AZIP fixes that by making each previously-inserted root remain valid for the lifetime of the epoch's outbox entry.

## Specification

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119 and RFC 8174.

### Storage model

The Outbox storage MUST be changed from a single root per epoch to an ordered list of roots per epoch, while the nullifier bitmap MUST remain a single bitmap per epoch shared across every root for that epoch.

Before:

```solidity
struct RootData {
  bytes32 root;
  BitMaps.BitMap nullified;
}
mapping(Epoch => RootData) internal roots;
```

After:

```solidity
struct EpochData {
  bytes32[] roots;          // one entry per insert() call for this epoch
  BitMaps.BitMap nullified; // shared across every root of the epoch
}
mapping(Epoch => EpochData) internal epochs;
```

### `insert`

`insert(Epoch _epoch, bytes32 _root)` MUST append `_root` to `epochs[_epoch].roots` rather than overwriting the previous root. The index of the newly appended root (zero-based) MUST be emitted in the widened `RootAdded` event:

```solidity
event RootAdded(Epoch indexed epoch, uint256 indexed rootIndex, bytes32 root);
```

The caller authorization check (rollup-only) is unchanged.

### `consume`

`consume` MUST gain a `_rootIndex` parameter selecting which root of the epoch to verify inclusion against:

```solidity
function consume(
  DataStructures.L2ToL1Msg calldata _message,
  Epoch _epoch,
  uint256 _rootIndex,
  uint256 _leafIndex,
  bytes32[] calldata _path
) external;
```

The implementation MUST:

1. Revert with `Outbox__NothingToConsumeAtEpoch(_epoch)` if `_rootIndex >= epochs[_epoch].roots.length`.
2. Load `root = epochs[_epoch].roots[_rootIndex]` and revert with `Outbox__NothingToConsumeAtEpoch(_epoch)` if `root == bytes32(0)`.
3. Compute `leafId = (1 << _path.length) + _leafIndex` and revert with `Outbox__AlreadyNullified(_epoch, leafId)` if the bitmap entry for `leafId` is already set.
4. Verify merkle membership of `_message.sha256ToField()` against `root` using `_path` and `_leafIndex`.
5. Set the bitmap entry for `leafId` on the epoch-level bitmap. This guarantees a message consumed against one root of an epoch cannot be replayed against any other root of the same epoch.
6. Emit `MessageConsumed(_epoch, root, messageHash, leafId)`.

### View functions

The view surface MUST be updated as follows:

- `hasMessageBeenConsumedAtEpoch(Epoch _epoch, uint256 _leafId) -> bool` — signature unchanged. The result reflects the shared epoch-level bitmap.
- `getRootData(Epoch _epoch, uint256 _rootIndex) -> bytes32` — gains a `_rootIndex` parameter and MUST return `bytes32(0)` for out-of-bounds indices.
- `getRootCount(Epoch _epoch) -> uint256` — new view exposing the number of roots inserted for the given epoch.

### `IOutbox` interface

The `IOutbox` interface MUST be updated to reflect the new `consume`, `getRootData`, and `RootAdded` signatures, and to add `getRootCount`. Implementations MUST conform to the updated interface.

## Rationale

### Why share the nullifier bitmap across roots of an epoch

Each successive partial proof for an epoch necessarily covers a superset of the L2 transactions covered by the prior proof: a later proof extends the epoch with more transactions, it does not contradict earlier ones. The L2-to-L1 messages that appear in the tree therefore have stable leaf IDs across proofs (a leaf ID is determined by its position in the wonky tree, which is preserved as the tree grows). A message consumed against root `R0` MUST NOT be replayable against any later root `R1` of the same epoch, even though `R1` is a different value, because both `R0` and `R1` include the same message at the same leaf ID. Sharing a single bitmap per epoch is the simplest correct way to express this and avoids cross-root replay attacks.

### Alternatives considered

- **Bundle the consume call with the proof submission.** When a user requests the partial proof, the prover could be asked to atomically submit the proof and the user's exit `consume` in the same L1 transaction. This sidesteps the race entirely but requires bridge-level cooperation, only helps when the user themselves requested the partial proof, and does nothing for users whose exit happens to fall inside a partial proof requested by someone else. It is a useful complement to this AZIP, not a substitute.
- **Delay overwriting the root for a fixed L1 block window.** Keep only one root per epoch, but require a delay before the next `insert` for the same epoch can overwrite it. This still imposes a hard deadline on the user's L1 transaction and creates an awkward liveness/safety trade-off for proof submission cadence.
- **Do nothing.** Accept that affected users will retry, considering the likelihood of the race is low.

## Backwards Compatibility

This AZIP is a breaking change to the L1 `Outbox` API and MUST be shipped as part of a new Aztec rollup version, with a new Outbox contract deployed alongside the new rollup. Specifically:

1. The `consume` function signature changes; any L1 contract that calls `Outbox.consume` MUST be updated.
2. The `getRootData` view changes shape; any L1 contract or off-chain consumer that reads it MUST be updated.
3. The `RootAdded` event payload is widened with `rootIndex`; off-chain indexers MUST be updated to decode the new payload.
4. `getRootCount` is added but does not break existing callers.

Existing bridges deployed against the prior Outbox continue to work against the prior rollup version. Migration of bridges to the new rollup version follows the standard cross-version bridge migration path; this AZIP does not introduce a new migration mechanism.

## Test Cases

The following scenarios MUST be covered by tests in `l1-contracts/test/outbox/` and the corresponding TypeScript-side message consumption tests:

1. **Single root, single consume.** Insert one root for epoch `E`; consume one message; verify success and that `hasMessageBeenConsumedAtEpoch` returns `true`.
2. **Multiple roots, consume against the first.** Insert `R0` then `R1` for epoch `E`; consume a message present in `R0` with `rootIndex = 0`; verify success.
3. **Multiple roots, consume against a later root.** Insert `R0` then `R1` for epoch `E`; consume a message with `rootIndex = 1`; verify success.
4. **Replay across roots is rejected.** After scenario 2, attempt to consume the same message with `rootIndex = 1` (where the same leaf ID also exists); verify revert with `Outbox__AlreadyNullified`.
5. **Out-of-bounds root index.** Insert one root; call `consume` with `rootIndex = 1`; verify revert with `Outbox__NothingToConsumeAtEpoch`.
6. **`getRootCount` reflects inserts.** After `n` inserts for epoch `E`, `getRootCount(E) == n`.
7. **`getRootData` returns zero for out-of-bounds.** `getRootData(E, getRootCount(E))` returns `bytes32(0)`.
8. **`RootAdded` event indexing.** The `rootIndex` emitted by successive `insert` calls is `0, 1, 2, …` for the same epoch.

## Example Implementation

The changes required for the `Outbox`contract are contained in the following patch:

```diff
diff --git a/l1-contracts/src/core/messagebridge/Outbox.sol b/l1-contracts/src/core/messagebridge/Outbox.sol
index 00fea24cf9..6e0e8ad707 100644
--- a/l1-contracts/src/core/messagebridge/Outbox.sol
+++ b/l1-contracts/src/core/messagebridge/Outbox.sol
@@ -28,11 +28,14 @@ contract Outbox is IOutbox {
   using Hash for DataStructures.L2ToL1Msg;
   using BitMaps for BitMaps.BitMap;

-  struct RootData {
-    // This is the outHash in the root rollup's public inputs.
-    // It represents the root of the epoch tree containing all L2->L1 messages.
-    bytes32 root;
-    // Bitmap tracking which messages (by leaf ID) have been consumed.
+  struct EpochData {
+    // The set of outHashes inserted for this epoch. Each entry is the root of an epoch
+    // tree containing L2->L1 messages. Multiple roots may exist for a single epoch when
+    // `insert` is called more than once (e.g. partial epoch proofs followed by extensions).
+    bytes32[] roots;
+    // Bitmap tracking which messages (by leaf ID) have been consumed within this epoch.
+    // The bitmap is shared across every root of the epoch: a message consumed against one
+    // root cannot be replayed against another root for the same epoch.
     // Leaf IDs are stable across different epoch proof lengths, ensuring consumed
     // messages remain marked as consumed when longer proofs are submitted.
     BitMaps.BitMap nullified;
@@ -40,7 +43,7 @@ contract Outbox is IOutbox {

   IRollup public immutable ROLLUP;
   uint256 public immutable VERSION;
-  mapping(Epoch => RootData root) internal roots;
+  mapping(Epoch => EpochData) internal epochs;

   constructor(address _rollup, uint256 _version) {
     ROLLUP = IRollup(_rollup);
@@ -55,13 +58,19 @@ contract Outbox is IOutbox {
    *
    * @param _epoch - The epoch in which the L2 to L1 messages reside
    * @param _root - The merkle root of the tree where all the L2 to L1 messages are leaves
+   *
+   * @dev If called multiple times for the same epoch, each call appends a new root to that
+   * epoch's list of roots rather than overwriting the previous one. The index of the newly
+   * added root within the epoch is emitted in the `RootAdded` event.
    */
   function insert(Epoch _epoch, bytes32 _root) external override(IOutbox) {
     require(msg.sender == address(ROLLUP), Errors.Outbox__Unauthorized());

-    roots[_epoch].root = _root;
+    bytes32[] storage epochRoots = epochs[_epoch].roots;
+    uint256 rootIndex = epochRoots.length;
+    epochRoots.push(_root);

-    emit RootAdded(_epoch, _root);
+    emit RootAdded(_epoch, rootIndex, _root);
   }

   /**
@@ -72,6 +81,8 @@ contract Outbox is IOutbox {
    *
    * @param _message - The L2 to L1 message
    * @param _epoch - The epoch that contains the message we want to consume
+   * @param _rootIndex - The index of the root within the epoch (epochs may have multiple roots
+   * when `insert` is called more than once for the same epoch)
    * @param _leafIndex - The index at the level in the wonky tree where the message is located
    * @param _path - The sibling path used to prove inclusion of the message, the _path length depends
    * on the location of the L2 to L1 message in the wonky tree.
@@ -79,6 +90,7 @@ contract Outbox is IOutbox {
   function consume(
     DataStructures.L2ToL1Msg calldata _message,
     Epoch _epoch,
+    uint256 _rootIndex,
     uint256 _leafIndex,
     bytes32[] calldata _path
   ) external override(IOutbox) {
@@ -92,22 +104,23 @@ contract Outbox is IOutbox {

     require(block.chainid == _message.recipient.chainId, Errors.Outbox__InvalidChainId());

-    RootData storage rootData = roots[_epoch];
+    EpochData storage epochData = epochs[_epoch];
+    require(_rootIndex < epochData.roots.length, Errors.Outbox__NothingToConsumeAtEpoch(_epoch));

-    bytes32 root = rootData.root;
+    bytes32 root = epochData.roots[_rootIndex];

     require(root != bytes32(0), Errors.Outbox__NothingToConsumeAtEpoch(_epoch));

     // Compute the unique leaf ID for this message.
     uint256 leafId = (1 << _path.length) + _leafIndex;

-    require(!rootData.nullified.get(leafId), Errors.Outbox__AlreadyNullified(_epoch, leafId));
+    require(!epochData.nullified.get(leafId), Errors.Outbox__AlreadyNullified(_epoch, leafId));

     bytes32 messageHash = _message.sha256ToField();

     MerkleLib.verifyMembership(_path, messageHash, _leafIndex, root);

-    rootData.nullified.set(leafId);
+    epochData.nullified.set(leafId);

     emit MessageConsumed(_epoch, root, messageHash, leafId);
   }
@@ -123,19 +136,34 @@ contract Outbox is IOutbox {
    * @return bool - True if the message has been consumed, false otherwise
    */
   function hasMessageBeenConsumedAtEpoch(Epoch _epoch, uint256 _leafId) external view override(IOutbox) returns (bool) {
-    return roots[_epoch].nullified.get(_leafId);
+    return epochs[_epoch].nullified.get(_leafId);
   }

   /**
-   * @notice  Fetch the root data for a given epoch
-   *          Returns (0, 0) if the epoch is not proven
+   * @notice  Fetch the root data for a given epoch and root index
+   *          Returns 0 if the epoch has no root at the given index
    *
    * @param _epoch - The epoch to fetch the root data for
+   * @param _rootIndex - The index of the root within the epoch
    *
    * @return bytes32 - The root of the merkle tree containing the L2 to L1 messages
    */
-  function getRootData(Epoch _epoch) external view override(IOutbox) returns (bytes32) {
-    RootData storage rootData = roots[_epoch];
-    return rootData.root;
+  function getRootData(Epoch _epoch, uint256 _rootIndex) external view override(IOutbox) returns (bytes32) {
+    bytes32[] storage epochRoots = epochs[_epoch].roots;
+    if (_rootIndex >= epochRoots.length) {
+      return bytes32(0);
+    }
+    return epochRoots[_rootIndex];
+  }
+
+  /**
+   * @notice  Fetch the number of roots stored for a given epoch
+   *
+   * @param _epoch - The epoch to fetch the root count for
+   *
+   * @return uint256 - The number of roots inserted for this epoch
+   */
+  function getRootCount(Epoch _epoch) external view returns (uint256) {
+    return epochs[_epoch].roots.length;
   }
 }
```

The follow-up work required to ship the change includes:

- Updating `IOutbox` to match the new `consume`, `getRootData`, and `RootAdded` signatures and add `getRootCount`.
- Updating every caller to pass and track a root index.
- Regenerating tests in `l1-contracts/test/outbox/` and the message consumption tests for multi-root scenarios.

## Security Considerations

### Cross-root replay

The primary new attack surface is replay of a consumed message against a different root for the same epoch. Sharing a single nullifier bitmap across all roots of an epoch, keyed by the wonky-tree leaf ID, prevents this: leaf IDs are stable across partial-proof extensions of the same epoch, so a message that has been nullified once cannot be successfully consumed against any other root of that epoch.

### Storage growth and griefing

Because `insert` is gated to the rollup, an external attacker cannot grow `epochs[E].roots` arbitrarily. A misbehaving or buggy rollup could in principle insert many roots per epoch, but the same authorization domain already controls more impactful state and this AZIP does not change the trust assumption. No per-epoch root cap is required; if one is desired for defense-in-depth, it MAY be added as a constant.

### Out-of-bounds reads

`getRootData` returns `bytes32(0)` for out-of-bounds indices rather than reverting. `consume` reverts on out-of-bounds with the existing `Outbox__NothingToConsumeAtEpoch` error, matching today's "no root inserted" path so callers see a single, recognizable failure mode for "nothing to consume here".

### Interaction with partial-proof incentives

If partial-proof incentives lead to a high cadence of `insert` calls per epoch, the storage footprint per epoch grows linearly in that cadence. This is acceptable: each entry is a single `bytes32` and the growth is bounded by epoch length and the rollup's own behavior. Indexers and bridge tooling SHOULD treat `(epoch, rootIndex)` as the canonical identifier for a root rather than the root value alone.

## Copyright Waiver

Copyright and related rights waived via [CC0](/LICENSE).
