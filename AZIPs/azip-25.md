# AZIP-25: Activity Score for Full Epoch Proofs

## Preamble

| `azip` | `title` | `description` | `author` | `discussions-to` | `status` | `category` | `created` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 25 | Activity Score for Full Epoch Proofs | The activity score increases only when a prover proves a complete epoch | Amin Sammara (@aminsammara, amin@aztec-labs.com) | N/A | Draft | Core | 2026-09-02 |

## Abstract

The protocol gives each prover an activity score. A high score gives the prover more shares of the epoch reward. Today the protocol increases the score for any accepted epoch proof regardless of length. A prover without enough compute to prove a congested epoch can avoid an activity score drop by just proving the first checkpoint of an epoch. When a less congested epoch comes around that they can prove, they receive the same reward share as a prover who invested in scaling compute to prove congested epochs. This reduces the incentive for provers to add compute capacity. This AZIP closes that gap: the score only updates on a full epoch proof, the same condition that already gates reward eligibility.  

## Impacted Stakeholders

**Provers.** A prover must prove a full epoch to increase its score.

## Motivation


`RewardLib.handleRewardsAndFees` calls `updateAndGetShares` for every accepted proof. That function increases the activity score. The increase does not depend on the length of the proof, and the protocol accepts a proof of a single checkpoint.

A prover can therefore repeat these steps in each compute-heavy epoch:

1. Prove the first checkpoint of the epoch.
2. Submit the proof.
3. Receive the increment.
4. Wait for a less congested epoch.
5. Submit the proof and receive full rewards.

The result is that provers have imperfect incentives to scale compute exactly when the network needs the capacity most. 

## Specification

The key words "MUST", "MUST NOT" and "SHOULD" are to be interpreted as described in RFC 2119 and RFC 8174.

### Full epoch proof

A proof of epoch `E` whose last checkpoint is `end` is a **full epoch proof** if both conditions are true:

1. The epoch is closed: `E < currentEpoch`.
2. One of these is true:
   - `end` is the pending tip: `end == tips.getPending()`.
   - The next checkpoint belongs to a later epoch: `STFLib.getEpochForCheckpoint(end + 1) > E`.

The implementation MUST evaluate condition 1 first. Condition 2 reads checkpoint `end + 1`, and that checkpoint exists only if `end` is not the tip.

### Activity score update

`RewardLib.handleRewardsAndFees` MUST accept a boolean `fullEpochProof`.

- If the value is true, the function MUST call `booster.updateAndGetShares(prover)`.
- If the value is false, the function MUST call `booster.getSharesFor(prover)`.

### Configuration

`proofSubmissionEpochs` MUST be greater than zero, and the rollup constructor MUST reject zero.

## Rationale

The Aztec Network has seen short bursts of blockspace demand. Epochs with more transactions require more compute to prove. During those bursts, some provers submitted proofs covering only part of the epoch which is indicative of a prover without the compute to keep up at high throughput. 

While partial proofs do not earn any protocol rewards, they currently feed the activity score. The activity score is a mechanism whose entire point is to reward consistent proving, which means proving at whatever throughput the network is running at. This AZIP makes it such that a prover that cannot cover a full epoch proof loses score.  

## Backwards Compatibility

This change requires a new rollup deployment and therefore a governance proposal.

## Reference Implementation

<https://github.com/AztecProtocol/aztec-packages/pull/25370>

## Security Considerations

- **The window for an increase is one epoch.** With `proofSubmissionEpochs` set to 1, only a submission in epoch `N + 1` increases the score.
- **A zero `proofSubmissionEpochs` stops all increments.** The mechanism then becomes dead code without an error. The requirement in Specification prevents this deployment.

## Copyright Waiver

Copyright and related rights waived via [CC0](/LICENSE).
