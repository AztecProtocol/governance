# Aztec Improvement Proposal: Raise the GSE Proof-of-Possession Gas Cap to 300k

## Preamble

| `azip` | `title` | `description` | `author` | `discussions-to` | `status` | `category` | `created` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 33 | Raise the GSE Proof-of-Possession Gas Cap to 300k | Raises the GSE proof-of-possession gas cap from 250,000 to 300,000 to account for Osaka's modexp repricing. | Santiago Palladino (@spalladino, santiago@aztec-labs.com) | N/A | Draft | Core | 2026-10-05 |

## Abstract

The GSE verifies each new validator's BLS proof of possession when the rollup's entry queue is flushed. The verification runs in an external call capped at `proofOfPossessionGasLimit`, currently 250,000 gas. The cost of that verification varies by key, because hashing the public key to a curve point is a rejection-sampling loop that calls the modexp precompile. The cap was sized before Osaka, whose EIP-7883 roughly tripled the price of each of those modexp calls, and it was not revisited when Osaka activated. Under Osaka pricing, about 1 in 28,559 honestly generated keys now needs more than 250,000 gas, against about 1 in 4.2M before Osaka. This AZIP proposes one governance action, `GSE.setProofOfPossessionGasLimit(300_000)`, included in the v6 upgrade payload. At 300,000 the rate falls to about 1 in 2.48M, close to its pre-Osaka level.

## Impacted Stakeholders

**Sequencers (validators).** Validators who register new BLS keys are the main beneficiaries. Today a small share of honestly generated keys fail verification at the cap. The deposit is refunded and the validator is not admitted, so the operator has to generate a new key and enter the queue again. Raising the cap makes this about 87 times less likely. Validators already in the set are not affected.

**Staking providers and key tooling.** Providers that generate keys in bulk see fewer rejected registrations. The validator key CLI will also check new BLS keys locally against the verification cost and can pick a cheaper derivation candidate, and a read-only preflight helper checks a registration tuple against the live cap before submission. Both work with either cap.

**Rollup instances sharing the GSE.** The GSE is shared, so the new cap applies to every rollup instance that uses it, from the moment the action executes. A deposit whose verification genuinely fails (an invalid key) can use up to 50,000 more gas in the flush transaction than today. Valid keys cost the same as before, because the cap is a limit, not a charge.

## Motivation

### How the cap is used

`GSE._checkProofOfPossession` calls `Bn254LibWrapper.proofOfPossession{gas: proofOfPossessionGasLimit}(pk1, pk2, signature)`. If the call does not return `true`, the deposit reverts with `GSE__InvalidProofOfPossession`. The rollup's flush then refunds the stake to the withdrawer, emits `FailedDeposit`, and moves to the next entry, so the validator is not admitted. The GSE (`0xa92ecFD0E70c9cd5E5cd76c50Af0F7Da93567a4f` on mainnet) is immutable, but its owner, governance, can change the cap with `setProofOfPossessionGasLimit(uint64)`. Its default is 250,000.

### Why the cost varies per key

Verification has a fixed part and a per-key part:

- **Fixed, about 131k gas.** It is dominated by the 113,000-gas pairing check, plus two `ecMul` (12,000), two `ecAdd`, a keccak and ABI decoding.
- **Per key.** `BN254Lib.hashToPoint` loops until it finds a valid point. Each attempt hashes the public key with a counter to a candidate x. It rejects x ≥ p (about 81% of attempts) and otherwise computes a modular square root with the modexp precompile. Half of those have no root, and the loop continues. The number of attempts and the number of square-root calls are both random, and the loop has no upper bound.

The measured cost fits this model, where the cap must cover the minimum stipend (the smallest gas limit for which the call succeeds, about 1,730 gas above the gas the call uses):

```
min stipend ≈ 132,694 + 515·attempts + S·sqrtCalls + 0.096·attempts²
S = 4,580 under Osaka pricing (modexp 4,016 + 564 of arithmetic)
S = 1,902 under Prague pricing (modexp 1,338 + 564 of arithmetic)
```

The quadratic term is memory growth from the loop's allocations.

### What Osaka changed

Osaka's EIP-7883 repriced modexp. For the square-root input in this loop, each call went from 1,338 to 4,016 gas. Every other precompile on this path (pairing, `ecMul`, `ecAdd`) kept its price. The cap was set before Osaka and not revisited when Osaka activated, so the share of valid keys whose verification needs more than 250,000 gas rose by about 150 times.

Example: the public test key `sk = 57193` needs 95 attempts and 18 square-root calls. Its verification uses 214,891 gas under Prague pricing (minimum stipend 216,622) and 263,095 gas under Osaka pricing (minimum stipend 264,826). That key would have registered before Osaka and is rejected at 250,000 today. It fits under 300,000.

### Share of honest keys over the cap

The share is `P(min stipend > cap)` for a uniformly random key, summed over the exact joint distribution of attempts `a` and square-root calls `k`:

```
P(a, k) = C(a-1, k-1) · (1 - P_lt)^(a-k) · (P_lt/2)^(k-1) · (P_lt/2)
P_lt = P(x < p) = p / 2^256 = 0.189030554816
```

Each attempt is rejected with probability `1 - P_lt`, a square root fails with probability 1/2, and the last attempt is the one that succeeds. The minimum stipend uses the conservative model constants above, which upper-bound every measured vector.

| Pricing | Cap | Share over the cap | Percent of honest proofs that fail | 1 in | Expected per 1,000 registrations | Expected per 10,000 registrations |
| --- | --- | --- | --- | --- | --- | --- |
| Prague (before Osaka) | 250,000 | 2.37e-7 | 0.0000237% | 4,219,373 | 0.00024 | 0.0024 |
| Osaka (today) | 250,000 | 3.50e-5 | 0.0035% | 28,559 | 0.035 | 0.35 |
| Osaka (proposed) | 300,000 | 4.03e-7 | 0.0000403% | 2,484,286 | 0.00040 | 0.0040 |

At 300,000 the rate returns to the same order of magnitude as before Osaka.

Under the rules of the next scheduled Ethereum fork, local measurements give the same gas as Osaka on this path. These figures will be re-measured once that fork is live.

## Specification

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119 and RFC 8174.

1. Governance MUST execute `GSE.setProofOfPossessionGasLimit(300_000)` on the mainnet GSE (`0xa92ecFD0E70c9cd5E5cd76c50Af0F7Da93567a4f`).
2. The action SHOULD be included in the v6 upgrade payload, so that it is voted on and executed together with the rest of the v6 upgrade.
3. The action MUST NOT lower the cap. If the cap is already 300,000 or higher when the payload is deployed, the action SHOULD be omitted.
4. After execution, `GSE.proofOfPossessionGasLimit()` MUST return `300000`.
5. No contract code, other parameter, or verification logic changes. The BLS scheme, the domain separator and `hashToPoint` are unchanged, so every key that verifies today still verifies.

## Rationale

**Why 300,000.** It cuts honest keys over the cap by about 87 times, from 1 in 28,559 to 1 in 2.48M, which is close to the pre-Osaka rate of 1 in 4.2M. The only cost is that a deposit whose verification genuinely fails can use up to 50,000 more gas in the flush transaction.

**Why not more.** Higher caps lower the rate further, but the benefit is negligible and the per-entry worst case for a failing deposit grows with the cap:

| Cap (Osaka pricing) | Share of honest keys over the cap | Worst-case gas for a failing entry |
| --- | --- | --- |
| 250,000 | 3.5e-5 | 250,000 |
| 300,000 | 4.0e-7 | 300,000 |
| 500,000 | 9.6e-15 | 500,000 |
| 1,000,000 | 5.1e-33 | 1,000,000 |

500,000 or 1,000,000 would double or quadruple that worst case to remove a rate that is already around one key in millions. A failing entry with a typical key uses about 139k gas, the same as a valid verification, because the pairing check runs at the same price and returns false. Only a failing entry whose key needs a long `hashToPoint` loop uses the whole cap.

**No cap fits every key.** The loop is unbounded, so some valid keys will always exceed any finite cap. For example, the public test key `sk = 1314687` (116 attempts, 24 square-root calls) needs a minimum stipend of 303,525 gas under Osaka pricing. The aim is a rate low enough that tooling handles the rest. Key tooling screens keys before registration: a key whose `hashToPoint` needs at most 18 attempts fits within 250,000 with a 10% margin even if every attempt calls modexp, and 26 attempts fit within 300,000 with the same margin.

**Alternatives considered.**

- *Keep 250,000 and rely on tooling.* Tooling helps new registrations, but keys generated by other software, or before the tooling change, would still be rejected at the Osaka rate.
- *Change the verifier.* The GSE is immutable, and a bounded hash-to-curve would change the proof-of-possession scheme. A parameter change is enough.

## Backwards Compatibility

Fully backwards compatible. Raising the cap only allows verifications that need between 250,000 and 300,000 gas to succeed. Every key that verifies under 250,000 verifies under 300,000 at the same cost. There are no ABI, storage layout or contract code changes. The change applies to all rollup instances that use the GSE, from execution onward. Keys already in the validator set are unaffected.

## Test Cases

Selected vectors from the calibration fixture. Every `sk` is a public test scalar, not a validator key. Gas is the minimum stipend for `Bn254LibWrapper.proofOfPossession`.

| `sk` | attempts | sqrt calls | Prague min stipend | Osaka min stipend | Osaka at 250k | Osaka at 300k |
| --- | --- | --- | --- | --- | --- | --- |
| 12 | 1 | 1 | 135,101 | 137,779 | fits | fits |
| 11 | 31 | 3 | 154,420 | 162,454 | fits | fits |
| 13154 | 102 | 10 | 205,159 | 231,939 | fits | fits |
| 57193 | 95 | 18 | 216,622 | 264,826 | rejected | fits |
| 241572 | 128 | 19 | 236,199 | 287,081 | rejected | fits |
| 693083 | 97 | 23 | 227,193 | 288,787 | rejected | fits |
| 1314687 | 116 | 24 | 239,253 | 303,525 | rejected | rejected |

Execution checks:

1. Before execution, `GSE.proofOfPossessionGasLimit()` returns `250000` and `GSE.owner()` is governance.
2. After the v6 payload executes, `GSE.proofOfPossessionGasLimit()` returns `300000`.
3. A registration with `sk = 57193` that fails at 250,000 succeeds at 300,000.

## Reference Implementation

- Measurements, cost model and calibration vectors: aztec-packages PR [#25600](https://github.com/AztecProtocol/aztec-packages/pull/25600) (`l1-contracts/test/shared/bn254-pop-gas/` and `l1-contracts/test/fixtures/bn254_pop_gas_vectors.json`). The measured `Bn254LibWrapper` runtime code matches the wrapper created by the mainnet GSE (`0x656F9140B9e2d3769D47b575512d46039dCab4D3`), apart from the compiler metadata.
- Governance action: aztec-packages PR [#25598](https://github.com/AztecProtocol/aztec-packages/pull/25598), stacked on the v6 upgrade payload in PR [#25496](https://github.com/AztecProtocol/aztec-packages/pull/25496). It adds `GSE.setProofOfPossessionGasLimit(300_000)` as the last action of `V6UpgradePayload`, rejects any value that would not raise the cap, and checks the new cap in the upgrade simulation and in a full governance execution test.

## Security Considerations

- **Gas used by failing entries.** The cap bounds the gas a single deposit's verification can use inside a flush. Raising it to 300,000 raises that bound by 50,000 per failing entry. Valid keys cost the same.
- **No change to verification.** The proof-of-possession check, the domain separator and the curve operations are unchanged. A higher cap cannot make an invalid proof verify. It only gives valid proofs with expensive `hashToPoint` loops enough gas to finish.
- **Shared GSE.** The cap is a single value on the shared GSE. It applies to every rollup instance from execution onward, including the v5 rollup while it accepts deposits.
- **Monitoring the cost.** This change was needed because a fork repriced a precompile on this path. The cap SHOULD be re-checked whenever a fork reprices modexp, the BN254 precompiles or memory, using the calibration vectors above.
- **Residual rate.** About 1 in 2.48M valid keys still exceeds 300,000. Key tooling SHOULD screen keys against the live cap before registration.

## Copyright Waiver

Copyright and related rights waived via [CC0](/LICENSE).
