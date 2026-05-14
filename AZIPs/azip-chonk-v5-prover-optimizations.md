# AZIP-13: Chonk v5 Prover Optimizations

## Preamble

| `azip` | `title`                       | `description`                                                                                          | `author`                       | `discussions-to` | `status` | `category` | `created`  |
| ------ | ----------------------------- | ------------------------------------------------------------------------------------------------------ | ------------------------------ | ---------------- | -------- | ---------- | ---------- |
| 13 | Chonk v5 Prover Optimizations | A catalog of circuit-level optimizations to the Chonk client-side proving stack shipped in version 5.  | Luke Edwards (@ledwards2225)   | N/A              | Draft    | Core       | 2026-05-13 |

## Abstract

This AZIP catalogs the largest circuit-level optimizations to the Chonk client-side proving stack shipped in v5, targeting prover time, proof size, and native verification time. It is not an exhaustive list of v5 backend changes; smaller changes that ship with the release are not individually cataloged here. Each optimization is specified independently below. Additional major optimizations may be appended during the `Draft` and `RFD` phases.

## Impacted Stakeholders

**Provers.** Every Chonk-flavored verification key changes under v5. Provers MUST re-derive and re-pin VKs before producing or verifying any v5 proof. Aggregate per-transaction proving-time savings depend on the flow but are positive on every measured flow.

**Sequencers.** Sequencers MUST upgrade their node software in lockstep so that the new VK set is loaded. Any L1 verifier contract changes accompanying the v5 release are out of scope of this AZIP and are tracked separately as part of the v5 rollout.

**App Developers and Wallets.** No application-visible change. Contract bytecode, contract artifacts, and the private-call ABI are unchanged. Wallets that pre-compute kernel proofs MUST upgrade their PXE in lockstep.

## Motivation

These optimizations target faster client-side proving and improved network throughput. Per-optimization motivation is stated in the corresponding subsections.

## Specification

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "NOT RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119 and RFC 8174.

### Catalog

| ID | Optimization | Scope |
| --- | --- | --- |
| O1 | Compressed Poseidon2 internal layout | Mega flavor, all Chonk-flavored circuits |
| O2 | Multi-app private kernel variants | Private kernel `init` and `inner` |
| O3 | Delayed / batch merge protocol | Goblin merge, hiding kernel |
| O4 | Joint MegaZK + translator sumcheck and PCS | Final Chonk proof |
| O5 | Fixed lookup tables in recursive IPA verifier | Root rollup recursive IPA |

### Optimization O1: Compressed Poseidon2 internal layout

The Poseidon2 hash permutation embedded in Chonk's main flavor (Mega) previously used one row of trace per partial round, 73 rows per full permutation. The compressed layout encodes four consecutive partial rounds in a single row by committing only the state lane that the S-box acts on; the other three lanes are pinned implicitly by an algebraic relation between adjacent rows. The whole permutation now fits in 27 rows. The mathematical permutation (state size, round counts, S-box, matrices) is unchanged, so any code that computes Poseidon2 in or out of circuit sees identical hash values.

Mega circuits dominate Chonk proving time and Poseidon2 dominates Mega arithmetic.

- The Mega-flavor Poseidon2 permutation MUST be encoded in 27 trace rows per permutation. The Ultra-flavor Poseidon2 encoding MUST NOT change.
- The mathematical Poseidon2 parameters and outputs MUST be unchanged from v4.

**Rationale.** Four-at-a-time is the largest compression factor whose algebraic check fits in a single gate row. Smaller factors produce strictly larger traces; larger factors don't fit. Ultra stays at the direct layout because the compression depends on Mega-specific custom gates, and Ultra's external use cases don't benefit enough to justify importing them.

**Security.** The compressed relation never recovers the hidden lanes at runtime; it ties adjacent rows together through algebraic equalities whose injectivity (under a pairwise-distinctness side condition on the internal-matrix parameters) forces the lanes to their correct values. A formal soundness argument accompanies the implementation and is expected to be audited as part of the v5 audit cycle.

### Optimization O2: Multi-app private kernel variants

The private kernel previously verified one application call per invocation, so a transaction touching `N` app calls required `N` kernel iterations. v5 adds variants of the `init` and `inner` kernels that absorb 2 or 3 app calls per invocation. The PXE selects the largest variant that fits the remaining work at each step, capped at 3 apps per iteration. The public-input outputs of an `N`-app variant are bit-identical to those produced by the corresponding chain of single-app kernels. The variants are functionally equivalent compositions of the same per-app accumulator, packed into one circuit.

Each kernel iteration carries per-circuit overhead (folding, witness commitment) that is independent of how much work the iteration does. Batching `N` apps into one iteration amortizes that overhead and removes `N − 1` iterations from the chain.

- The new variants MUST be registered in the kernel VK tree at indices 65 (`init_3`), 66 (`init_2`), 67 (`inner_2`), 68 (`inner_3`).
- The maximum number of app calls per kernel invocation MUST be 3.
- The public-input output of an `N`-app variant MUST equal that produced by the equivalent chain of single-app kernels on the same inputs.
- Every downstream kernel circuit (`inner`, `reset`, `tail`, `tail_to_public`) MUST accept any of the new variants as a valid predecessor.

**Rationale.** Per-app-count variants with distinct VKs were chosen over a single padded maximum-apps kernel for two reasons. First, a padded 3-app kernel proving a single app would be strictly more expensive than the existing single-app kernel, defeating the optimization. Second, distinct VKs let the recursive verifier dispatch on VK index rather than on a runtime app-count input, eliminating a class of dispatch-mismatch attacks.

**Security.** Because dispatch happens by VK index rather than by a runtime input, a prover cannot prove under a smaller variant while claiming a larger app count or vice versa. The downstream allow-list MUST be extended consistently across every consumer.

### Optimization O3: Delayed / batch merge protocol

The Goblin merge sub-protocol used to run once per IVC accumulation step, for every accumulated app and kernel circuit. v5 defers those per-step merges: each kernel updates a running hash over the incoming circuit's op-queue commitments, and a single batch merge runs once at the end of accumulation. The hiding kernel (the circuit that finalizes IVC state) recursively verifies the batch merge and exposes the resulting aggregate-table commitments through its public inputs. A separate single-step merge is still run for the hiding kernel's own contribution to the op queue, since that happens after the batch is closed.

Per-step merge prover/verifier costs that previously scaled linearly with IVC chain length are replaced by one hash update per kernel plus one batch merge whose cost depends only on the maximum supported chain length, not the actual one.

- The single-step Goblin merge MUST NOT run on per-circuit accumulation steps. Kernels MUST maintain a running hash over op-queue commitments that the final batch merge proof is bound to.
- The hiding kernel's public inputs MUST expose the aggregate-table commitments produced by recursively verifying the batch merge.
- The hiding kernel's own contribution to the op queue MUST still be merged via the single-step protocol, and that proof MUST appear in the outer Chonk proof. The batch merge proof is only verified recursively and MUST NOT appear in the outer Chonk proof.

**Rationale.** Per-circuit merges paid a fixed cost on every accumulation step regardless of how much there was to merge. Deferring lets the chain pay one hash update per step and one batch cost at the end. The hiding kernel is the natural home for batch verification because it already finalizes IVC state.

**Security.** Soundness relies on the batch merge being equivalent to the sequence of per-step merges it replaces and on every accumulated circuit being bound to the running hash that the batch proof references. Implementations MUST audit that no per-step merge call survives in the accumulation path and that the batch merge consumes every committed subtable.

### Optimization O4: Joint MegaZK + translator sumcheck and PCS

The MegaZK flavor (used to prove the hiding kernel) and the translator circuit previously had independent sumchecks and independent polynomial commitment openings. v5 batches them into a single joint sumcheck and a single joint Shplemini/KZG opening. The two relations are combined under a single batching challenge derived from the shared transcript after all pre-sumcheck commitments are absorbed; the smaller circuit is embedded into the larger circuit's round count via extension-by-zero in the unused rounds.

One full sumcheck and one full polynomial-commitment opening are eliminated from every Chonk proof (fewer rounds, smaller proof, less verifier work).

- A Chonk proof MUST consist of five segments: hiding-kernel Oink, single-step merge proof, ECCVM proof, IPA proof, and joint proof (translator Oink plus joint sumcheck plus joint Shplemini/KZG).
- The relation-batching challenge applied to the translator's contributions MUST be derived from the shared Fiat-Shamir transcript after all pre-sumcheck commitments are absorbed.
- The joint sumcheck MUST run for the larger of the two circuits' round counts; the smaller circuit's contributions MUST be handled by extension-by-zero in the rounds it does not occupy.
- Zero-knowledge MUST be provided by joint Libra masking in the sumcheck and a Gemini masking polynomial in the Shplemini reduction.

**Rationale.** Independent sumchecks and openings made sense when the two circuits were developed independently. Once their proof shapes were compatible, batching them under a single challenge was strictly cheaper. The five-segment proof structure preserves the independence of the remaining segments (Oink, merge, ECCVM, IPA) so downstream verifiers can compose against them as before.

**Security.** Soundness reduces to the independent soundness of the MegaZK and translator relations combined under a verifier-supplied batching challenge. That challenge MUST be drawn after both circuits' commitments are absorbed into the transcript. The joint zero-knowledge masking MUST cover both circuits' witness contributions.

### Optimization O5: Fixed lookup tables in recursive IPA verifier

The recursive IPA verifier (the circuit that verifies the inner-product argument inside the root rollup) used to spend most of its gates on a 32,768-point multi-scalar multiplication over the Grumpkin SRS. v5 replaces the per-element ROM-table method previously used for those scalar multiplications with 8-bit fixed plookup tables, exploiting the fact that the SRS is fixed at protocol genesis and known to the verifier. The first SRS element is still multiplied via the legacy method to keep the lookup row count within 2²³. Native (non-recursive) IPA verification is unchanged.

Root-rollup active gate rows drop from about 12.9M to 6.35M, halving the dyadic size of the largest recursive circuit in the stack from 2²⁴ to 2²³.

- The root rollup VK changes; native IPA verification is unchanged.
- Tables used to encode SRS multiples in the recursive verifier MUST be deterministic functions of the canonical Grumpkin SRS, reproducible by any verifier from the SRS alone. They MUST NOT depend on prover-supplied data.

**Rationale.** The MSM was the single largest contributor to root-rollup gate count, and the SRS does not change after genesis, so the verifier can pre-resolve any multiple. Fixed plookup tables exploit that directly. The 8-bit width is the largest setting whose total lookup row count fits the rollup's gate budget while approximately halving the MSM cost; splitting the first element off keeps the total within 2²³.

**Security.** The plookup tables MUST be reconstructible by any verifier from the canonical Grumpkin SRS without prover-supplied input. Because tables are constructed per proof rather than baked into the VK, prover and verifier MUST agree exactly on the SRS source, the table width, and the encoding scheme.

## Rationale

Per-optimization design rationale is stated inside the corresponding subsection under [Specification](#specification).

## Backwards Compatibility

Every Chonk-flavored verification key changes under v5. All nodes producing or verifying Chonk proofs MUST upgrade in lockstep; a v4 prover producing proofs against v5 VKs (or vice versa) will fail verification, and v4 and v5 VKs MUST NOT be mixed within a single proof chain.

Contract bytecode, contract artifacts, the private-call ABI, and the application-developer-facing Noir interface are all unchanged. No application redeployment is required.

Any L1 verifier contract changes accompanying the v5 release are out of scope of this AZIP and are tracked separately as part of the v5 rollout.

## Test Cases

A canonical set of IVC inputs covering the v5 circuit set is pinned at AZIP acceptance time. For each pinned flow, the verification key derived from the v5 circuit bytecode MUST equal the pinned VK, and the corresponding proof MUST verify against the pinned VKs.

## Reference Implementation

The reference implementation lives in `AztecProtocol/aztec-packages`. Each optimization landed via the following PR(s): O1 [22652](https://github.com/AztecProtocol/aztec-packages/pull/22652), O2 [23076](https://github.com/AztecProtocol/aztec-packages/pull/23076), O3 [22775](https://github.com/AztecProtocol/aztec-packages/pull/22775), O4 [21246](https://github.com/AztecProtocol/aztec-packages/pull/21246) / [21376](https://github.com/AztecProtocol/aztec-packages/pull/21376) / [21263](https://github.com/AztecProtocol/aztec-packages/pull/21263), O5 [22320](https://github.com/AztecProtocol/aztec-packages/pull/22320).

## Security Considerations

Every new or modified circuit MUST be bit-identical across builds: the same source, compiler, and dependency graph MUST produce the same VK regardless of thread count or build host. CI MUST gate v5 releases on a deterministic-VK check covering every new variant. Partial deployments where some nodes hold v4 VKs and others hold v5 VKs are forbidden by [Backwards Compatibility](#backwards-compatibility).

Per-optimization soundness analysis is stated inside the corresponding subsection under [Specification](#specification).

## Copyright Waiver

Copyright and related rights waived via [CC0](/LICENSE).
