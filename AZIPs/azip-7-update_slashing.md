# AZIP-7: Update Slashing Rules

## Preamble

| `azip` | `title`               | `description`                                                                                                       | `author`                                                  | `discussions-to`                                          | `status` | `category` | `created`  |
| ------ | --------------------- | ------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------- | --------------------------------------------------------- | -------- | ---------- | ---------- |
| 7      | Update Slashing Rules | Adds new slashing offenses for checkpoint-related proposer and attestor misbehavior, and revises existing offenses. | Santiago Palladino (@spalladino, santiago@aztec-labs.com) | https://github.com/AztecProtocol/governance/discussions/9 | Draft    | Core       | 2026-04-21 |

## Abstract

This AZIP updates the set of slashing offenses enforced by the Aztec protocol. It introduces new offenses covering checkpoint-related proposer misbehavior (submitting a block proposal after a checkpoint, invalid checkpoint proposals, block proposals containing clearly invalid transactions), a new offense on attestations (attesting to an invalid proposal), and revises existing offenses by replacing _Epoch Pruned_ with a _Data Withholding_ check and refining how _Validator Inactivity_ is measured and attributed.

## Impacted Stakeholders

**Validators.** Validators are directly affected: this AZIP expands the set of behaviors that can lead to stake being slashed. Proposers gain new slashing surface for checkpoint-related misbehavior. Attestors gain new slashing surface for attesting to invalid proposals and for data withholding. Conversely, validators are no longer exposed to prover failures.

## Motivation

Validators monitor each other for bad behaviour, and collect _offenses_ they see committed by others. When a validator is elected as a proposer, they _vote_ to slash the offenders they saw in the past epochs. This voting mechanism allows the network to slash for offenses that are not necessarily provable based on L1 evidence only.

The current rules predate the introduction of checkpoints and pipelined block-building, and they also entangle validator duties with prover liveness via the _Epoch Pruned_ offense. This AZIP addresses three gaps: (1) several classes of proposer misbehavior around checkpoints are not covered; (2) attestors who sign off on invalid proposals are not held accountable; and (3) committees can currently be slashed for failures that are outside their control (provers failing to prove a valid, data-available epoch). The proposed changes tighten attributions of fault and close these gaps.

For context, the current offenses in the system are the following:

### Current Offenses

#### Epoch Pruned

An epoch that is considered valid, as in all blocks in it can be confirmed to be correct after tx reexecution, that was not successfully proven within the proof submission window and was pruned. All committee members of the pruned epoch are penalized, since it's considered that they did not make the data available in time. This also triggers if the epoch cannot be confirmed to be valid since its data is not available for reexecution. This is an epoch-based offense.

#### Validator Inactivity

A validator failed to propose blocks or submit attestations during their assigned slots. Inactivity is measured over full epochs: if a validator's failure rate exceeds a configurable threshold for a number of consecutive epochs, they are slashed. This is an epoch-based offense targeting the individual inactive validator.

Note that each node decides whether the proposer or the attestor is at fault based on whether the proposal received at least one attestation: if the proposal received no attestations, then it's assumed it was invalid and the proposer is slashed, but if it received at least one, then validators are considered at fault.

#### Invalid Block Proposal

A proposer broadcast an invalid block proposal over the peer-to-peer network. The proposer who broadcast the invalid block is penalized. This is a slot-based offense.

#### Duplicate Proposal (Equivocation)

A proposer sent multiple conflicting block or checkpoint proposals for the same position. Since each slot has exactly one designated proposer, sending conflicting proposals is considered equivocation. The proposer who broadcast the duplicate is penalized. This is a slot-based offense.

#### Insufficient or Invalid Attestations

A proposer submitted a block to L1 without enough attestations from the validation committee, or with an invalid signature. The block proposer is penalized. This is a slot-based offense.

#### Attesting to a Descendant of a Block with Insufficient or Incorrect Attestations

A committee member attested to a block that was built on top of a known invalid ancestor. All committee members who attested to the descendant block are penalized. This is a slot-based offense.

## Specification

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119 and RFC 8174.

### New Offenses on Proposals

#### Submitting Block Proposal After Checkpoint

A proposer sent a block proposal after the checkpoint proposal had already been issued for the same slot. Once a checkpoint is proposed, no further block proposals SHOULD be sent. The proposer MUST be penalized. This is a slot-based offense.

#### Invalid Checkpoint Proposal

A proposer broadcast an invalid checkpoint proposal over the peer-to-peer network, such as one where the checkpoint header doesn't match the expected state, or does not follow from all prior block proposals in the slot. The proposer MUST be penalized. This is a slot-based offense, and an extension of the _Invalid Block Proposal_ offense.

#### Block Proposal With Invalid Transactions

A proposer broadcast a block proposal containing clearly invalid transactions, such as transactions with an incorrect chain ID. The proposer MUST be penalized. This is a slot-based offense. This is an extension to slashing for _Invalid Block Proposals_, which didn't account for this scenario.

### New Offense on Attestations

#### Attesting to an Invalid Proposal

A committee member attested to a checkpoint proposal that included an invalid block, where a block is considered invalid when the resulting state after executing it is different to that of the proposal. Detected by tracking invalid block proposals, and then tracking attestations to checkpoints in that slot. The attesting validator MUST be penalized. This is a slot-based offense. Rationale for this offense is to hold validators accountable if they fail to properly validate proposals.

### Changes to Existing Offenses

#### Epoch Pruned replaced by Data Withholding

The _Epoch Pruned_ offense is removed in favor of checking _Data Withholding_ after a slot. After a checkpoint is published, nodes check if the data for all transactions in it is available. If not, the set of validators who attested to that slot is considered at fault for not making the data available to the network. Slashing MUST apply even if the epoch gets pruned, to prevent committees from striking side deals with specific provers by only releasing transaction data to them.

We consider this an offense if `DATA_WITHHOLDING_TOLERANCE` seconds after checkpoint is mined on L1 (alternatively, after the end of the checkpoint's slot) the data (ie the txs included in the blocks of the checkpoint) is not found by the node.

This change allows us to remove the _Epoch Pruned_ offense, since validators should not be on the hook for ensuring that at least a prover fulfills their duties. Validators are only expected to validate proposals and make data available in time on the p2p network, which is now checked by other offenses.

#### Validator Inactivity

We propose two changes to the existing offense. First, performance is tracked at the end of every epoch rather than waiting for the epoch to be proven.

Second, block re-execution is used to independently verify whether a proposal was valid, correctly attributing fault between the proposer and the attestors, instead of relying on attestation count as a proxy. This is now viable since all nodes re-execute blocks, so each node knows for certain whether a proposal was valid or not and should have been attested.

### Parameters

The following protocol parameters are introduced or referenced by this AZIP.

| Parameter                    | Value              | Description                                                                                                                                                                                    |
| ---------------------------- | ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `DATA_WITHHOLDING_TOLERANCE` | 3 L2 slot duration | Time after checkpoint mining (or end of checkpoint slot) after which, if transaction data is not found, the validators who attested to that slot are considered at fault for data withholding. |

## Rationale

The design preserves the existing voting-based slashing mechanism: proposers vote to slash offenders they observed in prior epochs, which allows the network to punish offenses that are not provable from L1 evidence alone. The new offenses extend this same mechanism to checkpoint-related misbehavior and to attestors who rubber-stamp invalid proposals, closing accountability gaps introduced alongside checkpoints.

Replacing _Epoch Pruned_ with _Data Withholding_ narrows validator responsibility to what validators actually control — validating proposals and serving data on the p2p network — and removes their exposure to prover liveness. The explicit "slash even if the epoch is pruned" rule is motivated by preventing side deals where a committee withholds data from the broader network while releasing it to a specific prover.

For _Validator Inactivity_, using block re-execution for fault attribution replaces the prior heuristic (using attestation count as a proxy for proposer-vs-attestor fault) with a direct check. This is now practical because all nodes re-execute blocks. The previous heuristic was easy to game: any node that had two validator addresses in the committee could create an attestation for their own block even if they did not release the relevant data, flagging all other validators as at fault. As for moving measurement to the end of each epoch, this allows for punishing inactive validators regardless of prover availability, and reduces the time to trigger the slash.

## Backwards Compatibility

This is a consensus-layer rule change. All nodes MUST upgrade in lockstep: nodes running the old rule set would neither detect nor vote for the new offenses, and would continue voting for offenses after being removed. Running a mixed network would cause divergent slashing outcomes across proposers. Hence we propose aligning this with the v5 upgrade.

## Security Considerations

**False positives for data withholding on congested p2p network.** If a node fails to gather all txs for a given checkpoint due to p2p network congestion, even if the committee did make all data available, they will consider the committee at fault for data withholding. This creates a risk of false positives in cases of genuine p2p congestion.

## Copyright Waiver

Copyright and related rights waived via [CC0](/LICENSE).
