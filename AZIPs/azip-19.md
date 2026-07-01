# AZIP-19: Committee-Attested Fees

## Preamble

| `azip` | `title`                | `description`                                                                                           | `author`                                 | `discussions-to` | `status` | `category` | `created`  |
| ------ | ---------------------- | ------------------------------------------------------------------------------------------------------- | ---------------------------------------- | ---------------- | -------- | ---------- | ---------- |
| 19     | Committee-Attested Fees | Commit each checkpoint's fee recipient and value in its header so fees are committee-attested, not prover-supplied. | Mitchell Tracy (mitchell@aztec-labs.com) | -                | Accepted    | Core       | 2026-06-18 |

## Abstract

Per-checkpoint fee data (`recipient`, `value`) currently reaches L1 as prover calldata bound only by the epoch proof. The fee `value` MUST instead be committed in the checkpoint header at propose time, joining the `coinbase` (recipient) the header already commits. At proof submission the prover MUST supply the full checkpoint headers; L1 MUST rehash each with the existing `ProposedHeaderLib.hash` and require equality with the stored per-checkpoint header hash. Fee recipient and value MUST be read from these verified headers. `_fees` MUST be removed from the verifier public inputs and from the submission arguments. This adds no new storage and removes the verifier from the fee-integrity trust path.

## Impacted Stakeholders

**Sequencers.** At propose time a sequencer MUST set the new header field to the checkpoint's summed transaction fees, which it already computes. Because the committee signs over the header hash, the fee value becomes committee-attested.

**Provers.** A prover MUST include the full checkpoint headers in the epoch proof submission and MUST NOT supply `_fees`. Calldata grows by one full header per checkpoint.

**Wallets, Token Bridges, App Developers, Infrastructure Providers.** No change.

## Motivation

The verifier is treated as untrusted: a verifier that wrongly returns `true` MUST NOT enable theft. Today the fee `recipient` and `value` arrive as prover calldata constrained only by the epoch proof, so a forged proof accepted by a faulty verifier lets the prover redirect or inflate fees. The committee already signs the payload digest over the checkpoint header hash, and that hash already commits `coinbase` and is stored per checkpoint. Committing the fee value there too binds both halves of the fee data to the committee rather than to the proof, closing the theft path without new storage or new trust assumptions.

## Specification

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119 and RFC 8174.

**Header field.** The proposed-header structure MUST gain a field `accumulatedFees` holding the checkpoint's total transaction fees, and this field MUST be included in the header hash. The Solidity, Noir, and TypeScript header definitions and their hash functions MUST remain byte-for-byte equivalent, and the header-length constants MUST be updated to match.

**Submission.** The epoch-proof submission arguments MUST include the array of proposed headers for the proven range and MUST NOT include `_fees`. For each checkpoint `i` in the range, the contract MUST require that hashing `headers[i]` with `ProposedHeaderLib.hash` equals the stored header hash for that checkpoint; submission MUST revert otherwise.

**Fee derivation.** For each verified header the fee recipient MUST be its `coinbase` and the fee value MUST be its `accumulatedFees`. Reward accounting MUST read recipient and value from these verified headers. All other reward logic is unchanged.

**Public inputs.** `_fees` MUST be removed from the verifier public inputs. The verification key MUST be regenerated for the new public-input layout, and the off-chain public-input construction and submission validation MUST match it.

## Rationale

Binding fees to the committee-signed header reuses the existing header hash, the existing per-checkpoint storage slot, and the existing `ProposedHeaderLib.hash`; the only additions are one header field and a rehash-and-compare per checkpoint. Carrying fees in the proof public inputs instead would leave integrity dependent on the verifier, which is the property this proposal removes. Supplying full headers at submission rather than storing fee data separately avoids any new storage.

## Backwards Compatibility

The header layout and hash change, so the verification key changes and pinned constants and keys MUST be regenerated; sequencers, provers, and the L1 contracts MUST upgrade together. Fee value becomes sequencer-asserted and committee-attested rather than proof-derived. Submission calldata grows by one full header per checkpoint; this MUST be confirmed to remain under the L1 block gas limit at the maximum of 32 checkpoints per epoch.

## Test Cases

- A submission whose header `coinbase` or `accumulatedFees` does not reproduce the stored per-checkpoint header hash MUST revert.
- A submission whose headers reproduce the stored hashes MUST credit rewards to each `coinbase` exactly as before this change.
- The Solidity, Noir, and TypeScript header hashes MUST agree over random headers, including the `accumulatedFees` field.
- An end-to-end sequencer-to-prover-to-reward flow MUST distribute fees correctly with `_fees` removed.

## Reference Implementation

On-chain: add `accumulatedFees` to `ProposedHeader` and its `hash()` in `ProposedHeaderLib.sol`; mirror the field and hashing in `checkpoint_header.nr` and `checkpoint_rollup_public_inputs_composer.nr`, bumping header lengths in `constants.nr`; add the headers array to the submission arguments and the rehash-equality check in `EpochProofLib.sol`, dropping `_fees`; source recipient and value from the verified headers in `RewardLib.sol`.

Off-chain: add `accumulatedFees` to the sequencer header class (fields, serde, `hash()`, schema, `empty`, `random`) and populate it at propose with the checkpoint's summed transaction fees; in the prover node, add the headers array to the submission arguments, drop `fees`, source headers from the proposed checkpoints, and align the public-input construction and submission validation with the new layout.

## Security Considerations

The four header hash implementations — Solidity `ProposedHeaderLib.hash`, Noir `checkpoint_header.nr`, TypeScript `CheckpointHeader.hash`, and the pinned verification keys — MUST stay in exact agreement; any divergence either bricks submission or reopens a binding gap. With fees read from committee-attested headers, fee integrity no longer depends on the verifier returning a correct result. The maximum per-epoch calldata growth MUST be validated against the L1 block gas limit before deployment.

## Copyright Waiver

Copyright and related rights waived via [CC0](/LICENSE).
