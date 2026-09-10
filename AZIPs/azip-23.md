# AZIP-23: Introduce a Protocol Fee Margin

## Preamble

| `azip` | `title`                         | `description`                                                                                                                                        | `author`                                         | `discussions-to` | `status` | `category` | `created`  | `requires` |
| ------ | ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------ | ---------------- | -------- | ---------- | ---------- | ---------- |
| 23     | Introduce a Protocol Fee Margin | Adds a governance-set margin to the mana base fee; the markup above operator cost goes to a governance-set fee recipient, burned by default          | Amin Sammara (@aminsammara, amin@aztec-labs.com) | N/A              | Draft    | Economics  | 2026-07-06 |            |

## Abstract

Aztec prices transactions at operator cost. The mana base fee is `cost × congestionMultiplier`, where `cost = sequencerCost + proverCost`, an ETH denominated number that reimburses sequencers and provers for L1 gas and compute. The congestion multiplier is exactly 1.0 at or below the mana target so at normal load, users therefore pay exactly cost. The token flow is therefore: users acquire AZTEC to pay it, and operators sell it to cover the same ETH-denominated bills. Protocol usage generates turnover, not demand. Meanwhile the RewardDistributor releases 500 AZTEC per checkpoint into circulation whether the chain is empty or full. Token holders fund the entire operator subsidy through this supply growth, and adoption never relieves them: the fee system is priced so that usage contributes nothing towards funding the network.

This AZIP makes two changes:

1. **A protocol margin `μ`.** The mana base fee becomes `cost × (1 + μ) × congestionMultiplier`. Operators continue to receive exactly cost from the fee waterfall, plus the unchanged block reward. The markup above cost (`μ × cost` per mana, plus any congestion premium) goes to the protocol.
2. **A configurable fee recipient.** Today the protocol sends burned fees to `BURN_ADDRESS`, a compile-time constant in `RewardLib.sol`. This AZIP replaces the constant with a governance-set `protocolFeeRecipient` address held in rollup config and read at distribution time. At deployment the recipient is the current burn address, so the markup is burned. Governance can later redirect the markup, for example to the RewardDistributor or a protocol treasury.

The markup per mana is constant below the mana target. The markup collected per checkpoint is `μ × cost × manaUsed`. It grows in proportion to mana used, from zero on an empty chain to `μ × cost × manaTarget` at target. Above target, the congestion premium adds on top. The block reward is not modified.

This AZIP deploys at `μ = 0`, which is bit-identical to the current system. Governance then raises `μ` in rate-limited steps; the limiter bounds the fee multiplier `(1 + μ)`, so each step raises the pinned fee by at most ×3/2.

## Background

This section defines the protocol concepts this AZIP touches. Readers who know the fee system can skip it.

- **Mana.** Aztec's gas unit. Every transaction consumes mana. Circuits meter it; users cannot understate it.
- **Mana base fee.** The protocol-computed price per mana, in the fee asset (AZTEC). L1 pins it per checkpoint with an exact-equality check at propose. No valid block header can discount it.
- **Cost components.** `sequencerCost` (L1 gas the sequencer spends to publish) and `proverCost` (proof verification costs and `provingCostPerMana`, a governance-set proving compute cost). Both are ETH values per mana. A proposer-set oracle (`ethPerFeeAsset`, movable ±1% per checkpoint) converts them to AZTEC.
- **Congestion multiplier.** An EIP-1559-style multiplier. It is exactly 1.0 at or below the mana target and rises by up to ~12.4% per slot above it. Its job is to ration demand, not to raise revenue.
- **Checkpoint.** The unit of L1 publication, about 72 seconds. Each checkpoint carries one fee header and pays one block reward.
- **Fee waterfall.** `RewardLib.handleRewardsAndFees` splits each checkpoint's collected fees into three tranches: a burn tranche (the header's per-mana burn value times mana used), a prover tranche capped at prover cost, and a sequencer residual (everything left, including priority tips).
- **Block reward.** 500 AZTEC per checkpoint, split between sequencer and provers. The protocol does not mint it ad hoc. The RewardDistributor contract pays it from a pre-funded balance. Governance refills that balance through infrequent CoinIssuer mints. Each reward draw moves tokens from the distributor into circulation. Minting is therefore rare and lumpy, while circulating supply grows steadily. This AZIP accordingly speaks of circulating supply, not issuance: the per-checkpoint quantity the markup can offset is the 500 AZTEC the distributor releases into circulation.
- **Burn address.** `RewardLib.BURN_ADDRESS = address(bytes20("CUAUHXICALLI"))`, a compile-time constant. Transfers to it are irreversible. The fee asset has no `_burn` function, so these transfers do not reduce `totalSupply()`.

## Impacted Stakeholders

**Users.** Users pay `(1 + μ)` times the current cost-priced base fee. At `μ = 1` the fee doubles. Utilization today is near zero, so the absolute impact is small: roughly increasing median tx prices from 1.21 AZTEC to `(1 + μ)` × 1.21 AZTEC for a typical private transaction at reference prices. Fee predictability does not change. The base fee remains a single L1-pinned number per checkpoint, and wallet estimation flows keep the same mechanism.

**Sequencers.** Revenue does not change. The fee waterfall still pays the sequencer its own cost component plus all priority tips, and the checkpoint reward is untouched. The margin is levied on the user's payment above cost. It is never carved from operator income. Sequencer software MUST pick up the updated TypeScript fee mirror to predict fees correctly.

**Provers.** No change. The prover fee remains cost-capped (`min(manaUsed × proverCost, fee − protocolFee)`), which continues to bind at exactly `proverCost`. The prover share of the checkpoint reward is untouched.

**Token holders.** While the fee recipient is the burn address, the protocol gains a usage-proportional burn: at `μ = 1` and target utilization, about 135 AZTEC per checkpoint (about 59M AZTEC per year). The net change in circulating supply per checkpoint falls from a usage-invariant +500 to `500 − μ·cost·u`. It reaches net zero at `μ ≈ 3.7` at today's target throughput (75M mana), or at about 3.7 times today's throughput with `μ = 1`.

**Governance.** Gains two levers: the margin `μ` (rate-limited, floored at 0) and the `protocolFeeRecipient` address.

## Motivation

**The goal is to let users fund the network-issued operator subsidy instead of token holders, without touching the block reward**. Four facts about the current system make that impossible today:

1. **Supply growth is usage-invariant:**  The RewardDistributor releases 500 AZTEC per checkpoint into circulation, about 219M per year at full production.  This supply growth is what holders pay for the network's operation, and it is fixed.
2. **Users cannot contribute through costs:**  The base fee is a cost price. At or below the mana target, users pay exactly cost and operators receive exactly cost. Nothing is left over for the protocol to keep.
3. **Users cannot contribute through the market either:** A user acquires AZTEC moments before payment. The operator who receives it sells it to pay the same ETH-denominated bills: L1 gas and proving compute. Every token a user buys for fees, an operator sells. Usage moves tokens between parties. It does not create net demand for them.
4. **The congestion multiplier is not a structural capture tool:** It exists to exponentially kill off blockspace demand above the mana target. At or below the mana target, there is nothing to ration and therefore no structural capture is possible with congestion alone.

The governing identity holds per checkpoint: `ΔcirculatingSupply = reward − burn`. Users at or below target pay at most cost. Operators must receive at least cost. Users can therefore fund the network only if users are charged above cost.

Today, new token supply funds the entire operator subsidy, and users pay only cost. Under this proposal, users pay above cost, and the markup offsets the dilution holders bear, in proportion to usage. This AZIP claims no more than that.

Utilization is near zero today. The margin can therefore be introduced and raised at negligible present cost to users.

## Specification

The key words "MUST", "MUST NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", and "MAY" are to be interpreted as described in RFC 2119 and RFC 8174.

### Fee formula

The mana base fee computed in `FeeLib.getManaMinFeeComponentsAt` becomes:

```
costPerMana        = sequencerCost + proverCost   // unchanged, ETH wei per mana; per-component Ceil conversion unchanged
manaBaseFee        = costPerMana × (1 + μ) × congestionMultiplier   // the pinned per-mana fee; its fee-asset value is summedMinFee
protocolFeePerMana = summedMinFee − toFeeAsset(sequencerCost) − toFeeAsset(proverCost)   // μ·costPerMana + congestion premium
```

- `μ` is a new field in **`FeeConfig`**. The deployer sets its initial value. Governance adjusts it after deployment with `setProtocolMargin`. This is the same pattern as `provingCostPerMana`.
- `μ` is expressed in basis points (`μ_bps`). It is packed into 16 bits, bits 224 to 239 of **`CompressedFeeConfig`**. Today's `compress()` leaves the top 32 bits empty, so the storage layout does not change and bits 240 to 255 remain free for future fields. The 16-bit field caps `μ` at 6.55× (a fee multiplier of 7.55×), comfortably above the net-zero supply point of `μ ≈ 3.7` derived in Economics Considerations.
- The implementation applies `(1 + μ)` inside `congestionMultiplier()`. It MUST scale the `fakeExponential` factor to `(10000 + μ_bps) × 1e5` (**`FeeLib.sol:L360`**). This equals `1e9` at `μ=0` and is exact for all bps values. The implementation MUST NOT scale the `mulDiv` divisor. If both sites are scaled equally, the margin cancels and the fee does not change.
- Consequence: the congestion multiplier returned by `getManaMinFeeComponentsAt` is now scaled by `(1+μ)`. The uncongested baseline becomes `(1+μ) × 1e9` not `1e9`. A consumer that reads the multiplier as a pure congestion signal MUST correct for this scale.
- The implementation MUST compute `protocolFeePerMana` as one subtraction: the pinned fee minus the two converted operator costs. Then `fee − protocolFee = cost × manaUsed` holds exactly, to the wei. The implementation MUST NOT convert the margin and congestion tranches separately. The Ceil conversion is not additive, so separate conversion can differ by one wei and mis-pay operators.
- `protocolFeePerMana` is written to the existing uint64 `congestionCost` field of the fee header. The getter `getCongestionCost` is renamed `getProtocolFee`. The header stays one word. At `μ=1` and reference prices, the field has about ~1.0e7× headroom i.e. L1 gas prices, AZTEC price, congestion and `μ` have to rise together by this much to saturate the `protocolFeePerMana`. Saturation is graceful as `compress()` caps with `Math.min` rather than reverting.
- The `protocolFeePerMana` MUST NOT scale with priority tips which remain unchanged and swept by the sequencers.

### Fee recipient

- `RewardLib.sol` currently transfers the burn tranche to `BURN_ADDRESS = address(bytes20("CUAUHXICALLI"))`. This is a compile-time constant. This AZIP replaces the constant with a **`protocolFeeRecipient` address held in rollup config** . `RewardLib` reads this address at fee distribution time.
- The deploy-time default MAY be `address(bytes20("CUAUHXICALLI"))`. The default behavior is therefore identical to today: the `protocolFee` is burned.
- A new setter `setProtocolFeeRecipient(address)` MUST accept calls from Governance only. It MUST reject `address(0)`. It SHOULD emit an event with the old and the new recipient.
- **Gas cost.** The recipient read is one SLOAD in `handleRewardsAndFees`, which runs once per epoch-proof submission (`EpochProofLib.sol:141`) that extends the proven tip. Aside from proofs of partial epochs, this extra SLOAD cost is expected to be borne only by the first proof. A minuscule cost increase relative to the ~2e6 gas it costs today.

### Distribution

`RewardLib.handleRewardsAndFees` changes at one line. The protocol-fee line sends `protocolFeePerMana × manaUsed` to the configured `protocolFeeRecipient`.

### Governance of μ

- **Initial value:** The deployer sets the starting `μ_bps` in `FeeConfig`, as with `provingCostPerMana`. A start at `0` gives a deployment with a fee system identical to today. Increases then follow the limit below.
- **Increases:** The setter SHOULD bound each increase per 30-day window by ×3/2 **on the fee multiplier**, not on the margin: `(10_000 + μ_bps_new) × 2 ≤ (10_000 + μ_bps_current) × 3`. The bounded quantity is `(1 + μ)`, the number users actually pay, so every step raises the pinned fee by at most ×1.5 at constant costs and congestion. The window and step size match `setProvingCostPerMana` ([AZIP-2](./azip-2.md)).
- **Activation from zero:** No special case. The bound above already handles it: from `μ = 0` it permits any target up to 5,000 bps (fee ×1.5), the same ×3/2 rule as every later step.
- **Decreases:** Decreases SHOULD take effect immediately, with no rate limit. The minimum MUST be `0`. Because the limiter references the fee, re-raising after any decrease — to zero or to a small margin — proceeds at the same ×3/2-per-window pace; there is no slow-recovery dead zone at small margins.
- **Events:**  Each μ change SHOULD emit an event with the old and new values.

### Deployment

`FeeLib` and `RewardLib` are internal libraries. The compiler inlines them into the Rollup bytecode. This change therefore requires a new rollup deployment and a governance proposal. A config change is not sufficient. The new rollup deploys with `μ = 0` and with `protocolFeeRecipient` set to the current burn address. Fees and distribution are then identical to today. Governance then raises μ in steps, under the rate limits above. The markup from each step is visible on-chain before the next step.

### Client mirrors

The TypeScript mirror `stdlib/src/gas/fee_math.ts` MUST be updated to match the L1 code bit-exactly. The same factor and divisor exist at two sites in this file. Only the factor MUST be scaled, as on L1. The `μ` value MUST flow through the L1-config read in `rollup.ts` and into `fee_predictor.ts`.

## Rationale

**Separate rationing from funding:** The congestion multiplier is a rationing tool. Its purpose is to reduce demand above the mana target, so by design it is exactly 1.0 at or below target. As Motivation states, this is why usage funds nothing today: the only markup in the system is off at normal load. This AZIP does not change the rationing tool. The congestion multiplier stays a pure rationing signal, 1.0 below target. The funding job goes to a separate instrument. The margin `μ` is always on, does not depend on utilization, and sends its proceeds to the fee recipient.

**How the two tools compose:** The fee is `cost × (1 + μ) × congestion`. The formula is fully multiplicative: congestion scales the marked-up base, not the raw cost. Above target, the rationing premium is a percentage of what users actually pay. A high `μ` therefore does not weaken the rationing effect.

**Why a margin on the cost base:** Smallest change, bit-identical at `μ = 0`, waterfall reuse, dimensionless value.

**Why the fee recipient is configurable:** Whether the markup is burned, sent to the reward pool, or held in a treasury is a policy question, not a mechanism question.

**Why priority fees are never taxed:**  The tip is the sequencer's marginal-inclusion revenue. Taxing it drives the contention market to off-chain side payments. The markup rides entirely on the pinned base fee, which no valid header can discount, so it cannot be bargained away.

### Alternatives considered

**Full-base-fee burn (Ethereum's model):** This model burns all of what users pay. It pays operators only with the block reward and tips. Rejected: operator costs are mostly Ethereum gas. The fee tracks gas, but a flat reward does not. Near 8 gwei at the reference prices, the flat reward stops covering costs and operators stop producing.

**Cost-indexed rewards with full fee burn. Considered, not proposed:** This model makes the reward track operator costs, which repairs the previous failure. Three reasons against it. First, it moves circulating supply expansion the wrong way during a gas spike on a quiet chain. Second, it gains nothing over the simple margin. Supply growth depends only on what operators are paid and what users pay. Third, it is a more intrusive rebuild of the fee system.

**ETH-denominated additive wedge. Considered, not proposed:** The formula becomes `manaBaseFee = cost + b_protocol + congestion` - as opposed to `manaBaseFee = cost + μ×cost + congestion`. `b_protocol` is a governance-set ETH value per mana. Structurally it is a copy of `provingCostPerMana`. The difference is response to cost changes. The multiplicative margin scales with every component of `cost` i.e. L1 gas and `proverCostPerMana`. Whereas `b_protocol` is a fixed ETH denominated value that is captured by the protocol independent of the l1 or proving compute costs. Not proposed for two reasons: At 1 gwei, the L1-gas components are only about 30% of the base fee, and even less at sub-gwei l1 gas prices. Second, the additive term needs a repack of `CompressedFeeConfig` to be as expressive as `provingCostPerMana` i.e. 64bits - whereas the dimensionless `μ` can be adequately expressed in 32bits.

**Hardcoded burn with no recipient setter. Considered, not proposed:** Simpler, but every future policy change (recycle into rewards, treasury) becomes a rollup redeploy and full governance cycle.

## Backwards Compatibility

- **Deployment is a rollup redeploy** (governance proposal), not a config change.

## Test Cases

1. **Differential bit-identity at `μ = 0`:** The new `FeeLib` reproduces the current fee, header fields, and burn byte-for-byte across the existing `fee_data_points.json` trace and randomized excess-mana, gas, and price states.
2. **Waterfall identity:** For randomized (`μ`, gas, price, `manaUsed`): `fee − protocolFee = cost × manaUsed` exactly; prover fee = `proverCost × manaUsed`; sequencer fee = `seqCost × manaUsed` plus injected priority fees.
3. **Residual cap robustness:** When `summedMinFee` saturates uint128, operators still receive full cost; the shortfall reduces only the protocol-fee tranche.
4. **Margin setter semantics:** Increases bounded by `(10_000 + new) × 2 ≤ (10_000 + current) × 3` per window — from 0, targets up to 5,000 bps pass and 5,001 reverts; 30-day cooldown; immediate decrease to `0`; `μ` cannot go below 0; event emission.
5. **Recipient semantics:** The default `protocolFeeRecipient` equals `address(bytes20("CUAUHXICALLI"))`; only Governance can call `setProtocolFeeRecipient`; `address(0)` reverts; event emission; after a change, the next epoch-proof submission pays the protocol fee to the new recipient.

## Economics Considerations

**How the markup scales with usage:** The markup per mana is constant below the mana target: `μ × cost`. What scales is the total collected per checkpoint, `μ × cost × manaUsed`, which is proportional to mana used. An empty chain collects nothing. A chain at target collects `μ × cost × manaTarget` per checkpoint. Above target, the congestion premium stacks on top of this floor instead of being the only burn, so collection grows superlinearly there.

**Reference numbers:** At reference conditions (`ethPerFeeAsset` = 8,339,453 E12, the oracle snapshot of 2026-07-20, about $0.014 per AZTEC at ETH = $1,700; `manaTarget` = 75e6; observed median transaction 670k mana at 1.21 AZTEC; cost = 135.4 AZTEC per checkpoint at target) with `μ = 1`: users pay 270.9 AZTEC per checkpoint at target. Operators receive 635.4 (cost 135.4 from fees plus reward 500), unchanged from today. The protocol collects 135.4 per checkpoint, about 59M AZTEC per year at sustained target. With the burn-address recipient, the net change in circulating supply per checkpoint below target is `N(u) = 500 − 135.4·μ·u`: strictly decreasing in usage, net zero at `μ ≈ 3.7` at today's target throughput (~1.55 TPS), or at about 3.7 times today's target throughput with `μ = 1` (~5.7 TPS). Both figures assume an average 670k-mana transaction over 72-second checkpoints. Demand elasticity at these fee levels is unvalidated. This is why this AZIP recommends `μ` remain at 0 until appropriate user tx fees are validated.

**Effect of the recipient choice:** With the burn address, tokens leave circulation now and supply growth slows with usage. With the RewardDistributor, circulating supply does not shrink now; instead the reward pool refills, and future CoinIssuer mint requests shrink by the same amount. Both push long-run supply in the same direction; they differ in timing and in where the tokens sit meanwhile. With a treasury, supply is unchanged and Governance holds the funds.

**Effect of the AZTEC price on the markup:** The markup is set in ETH terms, so it always collects the same ETH-denominated amount per mana. The number of AZTEC tokens that represents moves opposite to the AZTEC price: a cheaper AZTEC means more tokens collected per unit of usage, a more expensive AZTEC fewer. Against the fixed 500-token reward, a lower AZTEC price therefore shrinks circulating supply faster (net zero is reached at lower throughput), and a higher price slower.

## Security Considerations

- **Price-oracle:** All fee quantities divide ETH values by `ethPerFeeAsset`. The proposer sets this price, and each checkpoint can move it at most ±1%. A proposer who moves the price down inflates all AZTEC-denominated fees, and `(1 + μ)` amplifies the effect on users.
- **Collusion:** The protocol fee is part of the pinned base fee. L1 checks the pinned fee by exact equality at propose time, so no valid header can state a lower fee. The circuits meter mana and enforce the fee debit. A user and a sequencer therefore cannot agree to avoid the protocol fee. The only negotiable value is the priority tip, which is deliberately exempt.
- **Stuffing:** A sequencer that fills its own checkpoints pays `(1 + μ) × cost` per mana. It recovers at most its own cost tranche and its share of the prover pool. Stuffing therefore loses money at every `μ ≥ 0`.
- **`provingCostPerMana` incentive (new under `μ`):** `provingCostPerMana` is a governance-set cost input. Each wei of overstatement pays provers one wei more per mana and sends `μ` wei more to the `protocolFeeRecipient`. The additive-wedge alternative removes this incentive; see Alternatives.
- **No way to reduce `totalSupply()`:** Even if the protocol fee is sent to the default burn address, the `totalSupply` is not reduced.

## Copyright Waiver

Copyright and related rights waived via [CC0](/LICENSE).
