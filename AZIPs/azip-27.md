# AZIP-27: Rate-Limited Exits by Staking Providers

## Preamble

| `azip` | `title` | `description` | `author` | `discussions-to` | `status` | `category` | `created` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 27 | Rate-Limited Exits by Staking Providers | Allows staking providers to exit delegators’ validator positions through attester accounts, subject to a shared rolling limit. | Rumata888 <innokentii@aztec-labs.com> | N/A — local draft | Approved | Core | 2026-09-09 |

## Abstract

This proposal lets staking providers initiate exits for the validator positions they operate by calling from the corresponding attester accounts. Delegators retain control of their funds. Provider-initiated exits are subject to a shared rolling limit of 5% of the remaining validator set over Governance’s current withdrawal delay, while withdrawer-initiated exits and slashing remain unrestricted by this limit.

## Impacted Stakeholders

**Staking providers.** Providers gain a way to end service without requiring the delegator to initiate withdrawal.

**Delegators and governance participants.** Providers gain the ability to exit delegated positions, reducing their current governance voting power. The limit restricts how quickly providers can do this, and the registered withdrawer retains control of the payout.

**Wallets and staking interfaces.** Interfaces need to support provider-initiated exits and distinguish them from withdrawals initiated by the stake owner.

## Motivation

Staking providers run validators with tokens supplied by delegators. The provider controls the attester account, but only the registered withdrawer can start an exit. The withdrawer may be the delegator's vault. This means the provider cannot end the arrangement on its own. If it simply stops validating, the delegator's stake may be slashed for inactivity.

But letting providers exit any number of positions at once would create another problem. A provider could exit many positions just before voting power is recorded for a governance proposal, reducing the delegators' power in that vote. This proposal lets providers initiate exits, but limits how quickly they can do so.

## Specification

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119 and RFC 8174.

**Authorization.** The rollup MUST provide an exit path for an active validator position callable by its attester address (`msg.sender == attester`).

**Exit limit.** The rolling window MUST equal Governance’s current withdrawal delay: `floor(votingDelay / 5) + votingDuration + executionDelay`. Before each provider-initiated exit, the number of such exits within this window, including the proposed exit, MUST NOT exceed 5% of the canonical rollup's effective validator set remaining after the proposed exit, rounded down. Membership is read from GSE and includes pinned and bonus positions belonging to that rollup, excluding queued deposits. The limit counts positions and is shared across all providers and attester accounts. Exits exactly one window old stop consuming allowance. Only successful removals count; failed transactions MUST leave usage unchanged. Batches MUST obey the same rule as sequential individual exits.

The remaining validator count MUST be at least the target committee size. If the pool shrinks so that recent usage exceeds the allowance, further provider-initiated exits MUST wait until the rule is satisfied. Withdrawer-initiated exits, slashing, and withdrawal finalization MUST bypass the new limit.

**Withdrawal.** A provider-initiated exit MUST remove the position through GSE and use the existing withdrawal delays and slashing rules. The attester MUST NOT gain authority to select the payout recipient; this remains with the registered withdrawer. Anyone may finalize once a recipient is selected and the delays have passed. Duties derived from historical validator snapshots MUST remain enforceable, including committees selected using `lagInEpochsForValidatorSet`.

**Deployment and continuity.** This feature requires a new rollup implementation. Only the canonical rollup MAY initiate these exits, and its address MUST agree with GSE's latest rollup. Exit usage MUST be stored in the rollup; each new rollup starts with empty history, without an activation delay. The 5% fraction MUST be fixed for the deployed rollup, while the window MUST follow Governance’s current configuration.

## General Implementation

The rollup checks attester authorization and its own shared exit allowance before withdrawing the position through GSE. It uses cumulative timestamp checkpoints stored in the rollup to count exits within the rolling window. Membership removal and allowance consumption happen in the same transaction.

The pending withdrawal can reuse the existing exit-record mechanism with `recipientOrWithdrawer` set to the withdrawer and `isRecipient = false`. The withdrawer subsequently selects a recipient through the existing withdrawal path. Provider-initiated exits should emit a distinct event so interfaces can identify their cause.

This approach retains the existing GSE and Governance contracts.

## Rationale

A sliding window directly limits removals over Governance’s withdrawal delay. A fixed reset would allow two full allowances on either side of the boundary. Copying the entry queue's per-epoch quotient would require fractional accounting at small pool sizes; adding a minimum of one exit could exceed the intended rate.

The allowance uses the remaining validator set so it tightens as the pool shrinks. It measures validator positions rather than token value, which can differ between positions after slashing. Using Governance’s withdrawal delay covers the voting duration, execution delay, and a buffer, and follows changes to those settings.

## Backwards Compatibility

The new authority applies to all effective positions on the upgraded canonical rollup, including bonus positions carried forward by GSE. There is no per-position opt-in. This change should be communicated to delegators before deployment. Positions pinned to older rollups retain their existing behavior.

Existing withdrawal rights, historical governance snapshots, and recorded votes remain unchanged. Interfaces should distinguish the new exit cause from slashing even if both use the same pending-withdrawal representation.

## Test Cases

- Only the position's attester can initiate the new exit, without gaining control of the payout recipient.
- Exits across different attesters share the limit, including within one block and at the window’s expiry boundary.
- Withdrawer exits and slashing succeed when provider allowance is exhausted.
- Failed, duplicate, and reentrant exits cannot consume or bypass allowance incorrectly.
- Changes in pool size and batch execution respect the remaining-pool limit and committee-size floor.
- Changes to Governance’s withdrawal delay change the window, counting older exits when it grows and releasing allowance when it shrinks.
- New rollups start with empty usage history, existing pending withdrawals remain usable on the old rollup, and a canonical/latest-rollup mismatch prevents provider-initiated exits.

## Security Considerations

The limit can slow disruption of governance participation, but cannot guarantee a vote's outcome. Exits before a voting-power snapshot can affect that vote; exits afterwards preserve its historical power. Governance configuration changes affect the window immediately: increasing it can bring older exits back into the count, while decreasing it can release allowance. Existing withdrawal deadlines remain unchanged. A rollup upgrade resets usage, so exits on either side of an upgrade can exceed a single rollup’s allowance within one window.

All available allowance can be used in one block, and one provider can consume it before others. Providers can still go offline while waiting, leaving delegators exposed to inactivity penalties. A minimum registered count does not guarantee enough responsive validators.

New admissions can increase the allowance, while voluntary withdrawals and slashing can shrink the pool independently. A compromised Ethereum attester key also gains the new exit capability, subject to the limit, but cannot redirect the funds.

The limit is enforced by the rollup. GSE does not distinguish provider-initiated withdrawals from other authorized rollup withdrawals, so a malicious governance upgrade could bypass the limiter.

## Copyright Waiver

Copyright and related rights waived via [CC0](/LICENSE).
