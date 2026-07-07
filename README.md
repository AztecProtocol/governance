# Aztec Governance

This is the canonical repository for all things Aztec Governance. It is the home to the AZIP and AZUP process:

- **[AZIPs (AZtec Improvement Proposals)](azip-process.md)** – the offchain process for proposing, iterating on, and socially validating changes to Aztec's protocols, standards, and governance.
- **[AZUPs (AZtec Upgrade Proposals)](azup-process.md)** – the onchain process for taking approved AZIPs through sequencer signaling, tokenholder voting, and onchain execution, turning proposed changes into live protocol upgrades.

Together, AZIPs and AZUPs form a structured pipeline for implementing changes within the Aztec Network in a transparent, controlled way.

## What's an AZIP?

AZIPs (AZtec Improvement Proposals) are version-controlled design documents that anyone can use to propose changes to the Aztec Network. For scope, categories, and the full process, see the [AZIP Process](azip-process.md). To start drafting, use the [AZIP Template](AZIPs/template.md).

## What's an AZUP?

AZUPs (AZtec Upgrade Proposals) bundle the implementations of one or more AZIPs that Core Contributors have approved for inclusion in the Aztec Network. For proposed changes to be considered for signaling by sequencers and voting by tokenholders, they must be formally proposed via the AZUP process.

Once an AZIP has been deemed properly specified, it is submitted by AZIP editors to the Core Contributors for final review. Core Contributors discuss AZIPs on a weekly basis during the Core Contributor Weekly call.

AZIPs are bundled together by Core Contributors into AZUPs. AZUPs include:

- List of AZIPs scheduled for inclusion
- Payload for any onchain changes

For the full process, see the [AZUP Process](azup-process.md). To start drafting, use the [AZUP Template](AZUPs/template.md).

## AZIP Editors

AZIP editors verify that proposals meet the criteria required to progress through the [AZIP Process](azip-process.md). Authors drive their own proposals through the process; editors are administrators, not decision-makers.

- [Josh Crites](https://github.com/critesjosh) [josh@aztec-labs.com](mailto:josh@aztec-labs.com)

## Contributing

Anyone can propose changes to the Aztec Network by submitting an AZIP. To get started:

1. Post your idea in [GitHub Discussions](https://github.com/AztecProtocol/governance/discussions) (under the "AZIP Ideas" category) to gather initial feedback
2. Use the [AZIP Template](AZIPs/template.md) to draft your proposal
3. Before requesting an editor review, run the `azip-editor-review` skill (in `.claude/skills/azip-editor-review/`) against your PR to catch the formatting, completeness, and process issues an editor would flag. See the [AZIP Process](azip-process.md#self-check-before-editor-review) for details.
4. Open a pull request to this repository. An editor will assign a number and review begins
5. Once peer review is complete, the PR is merged and the AZIP enters the repository

See the [AZIP Process](azip-process.md) for the full lifecycle and requirements.
