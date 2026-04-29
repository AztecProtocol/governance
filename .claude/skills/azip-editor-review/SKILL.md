---
name: azip-editor-review
description: Review an AZIP pull request from the perspective of an AZIP editor (administrative review only — formatting, completeness, process), check the linked discussion, and surface the manual edits that PR 18 (link-azip-to-discussion workflow) will eventually automate. Use when the user asks to "do an editor review" / "review this PR as editor" / "editor pass" on a PR that touches `AZIPs/**.md`. AZIP authors can also use it as a self-check before requesting review.
argument-hint: "<pr-number-or-url>"
---

# AZIP Editor PR Review

This skill runs the editor's review for an AZIP PR. The editor's role is **strictly administrative**: format, completeness, and process — never substantive. Editors cannot block on the merits of a proposal; that is Core Contributors' job during RFD review.

The output of this skill is:

1. A structured review of the PR against the editor checklist.
2. A review of the linked GitHub Discussion.
3. A list of manual edits to apply now that PR 18's workflow will automate once it lands.
4. A draft of the editor's review comment to post on the PR.

## Inputs

Invoke with a PR number (e.g. `/azip-editor-review 23`) or a PR URL. If neither is given, ask for it before proceeding. The repo is always `AztecProtocol/governance`.

Assume `gh` is already installed and authenticated against GitHub.

## Step 1 — Read the PR

Fetch the PR metadata and the changed AZIP files:

```bash
gh pr view <PR> --repo AztecProtocol/governance --json number,title,body,author,headRefOid,headRefName,state,files,reviews,comments
gh pr diff <PR> --repo AztecProtocol/governance
```

Identify the AZIP markdown file(s) changed under `AZIPs/`. Skip `AZIPs/template.md`. Read each changed file at the PR's head ref.

## Step 2 — Editor checklist

Run through this checklist for each changed AZIP. Report PASS / FAIL / N/A with a one-line note for each item. **Do not evaluate technical correctness or whether the proposal is a good idea — that is out of scope.**

### Preamble

- [ ] Preamble table is present and matches the template format (header row, separator, single data row).
- [ ] `azip` number is assigned and is the next sequential number (see Step 3).
- [ ] `title` is filled, ≤ 80 chars, does not include the AZIP number, does not include "standard" or variants.
- [ ] `description` is filled, ≤ 140 chars, does not include the AZIP number or "standard".
- [ ] `author` includes at least one entry with a GitHub username (`@handle`).
- [ ] `discussions-to` is a URL of the form `https://github.com/AztecProtocol/governance/discussions/<N>`, or a link to the aztec forum.
- [ ] `status` is `Draft` (PR is not yet merged).
- [ ] `category` is one of `Core`, `Economics`, `Standard`, `Informational`.
- [ ] `created` is a valid ISO 8601 date (yyyy-mm-dd).
- [ ] `requires` (if present) lists valid AZIP numbers.

### Required sections (per category)

All AZIPs need: Abstract, Motivation, Rationale, Backwards Compatibility, Copyright Waiver.

Additionally:

- `Core` and `Standard`: Specification + Security Considerations.
- `Economics`: Economics Considerations + Security Considerations.
- `Informational`: only the universal sections above.

For each required section: present? not a template placeholder? not a TBD?

### Style and markup

- [ ] No external links other than `forum.aztec.network` and `github.com/AztecProtocol/governance` (the only allowed externals per `azip-process.md`).
- [ ] References to other AZIPs use the `AZIP-N` form, with a relative markdown link on first reference.
- [ ] Assets, if any, live under `assets/azip-<N>/` and are referenced via relative paths.
- [ ] Copyright waiver text matches exactly: `Copyright and related rights waived via [CC0](/LICENSE).`
- [ ] No obvious grammar / spelling / markup errors. Note any.

### Process

- [ ] PR description is reasonable and a discussion link is present.
- [ ] Linked discussion exists in the `azip-proposals` category (Step 4 verifies).
- [ ] For Core/Standard/Economics: Security Considerations is non-trivial — the editor checks **presence and that reviewers have engaged with it**, not whether the analysis is correct. The reviewers (Core Contributors, peers) judge sufficiency.
- [ ] If the PR is being readied for merge to advance Draft → RFD: there is provable peer review in the PR comments and provable engagement from impacted stakeholders.

## Step 3 — AZIP number assignment

If the AZIP file is named `AZIPs/azip-N.md` and the preamble's `azip` field is empty or `TBD`, assign the next sequential number:

```bash
ls AZIPs/ | grep -E '^azip-[0-9]+\.md$' | sed 's/[^0-9]//g' | sort -n | tail -1
```

Also check open AZIP PRs to avoid colliding with a number that's already been claimed but not yet merged:

```bash
gh pr list --repo AztecProtocol/governance --state open --json number,title,headRefName
```

## Step 4 — Review the linked discussion

Parse `discussions-to` from the preamble. Fetch the discussion:

```bash
gh api graphql -f query='
  query($owner: String!, $name: String!, $number: Int!) {
    repository(owner: $owner, name: $name) {
      discussion(number: $number) {
        title body category { slug name } url
        labels(first: 50) { nodes { name } }
        comments(first: 50) {
          totalCount
          nodes { author { login } body createdAt }
        }
      }
    }
  }' -F owner=AztecProtocol -F name=governance -F number=<DISC>
```

Check:

- [ ] Discussion is in the `azip-proposals` category. (If not, this is a hard fail — the workflow in PR 18 will refuse to touch it. Ask the author to migrate the discussion or update `discussions-to`.)
- [ ] Discussion is reachable and not locked.
- [ ] Comments show non-author engagement. Summarize who has weighed in (logins + count) so the editor can decide if peer review is sufficient for an RFD merge.
- [ ] Note any open concerns raised in the discussion that haven't been addressed in the AZIP.

## Step 5 — Manual edits PR 18 will eventually automate

PR 18 adds a `pull_request_target` workflow that, on every AZIP PR push, will:

1. Apply the `has-azip` label to the linked discussion.
2. Prepend `**AZIP:** [AZIP-N](<pr-url>)` to the discussion body (idempotently).
3. Prefix the discussion title with `AZIP-N: `.

Until PR 18 is merged, the editor does this by hand. For the PR being reviewed, produce the three concrete edits the editor needs to make on the discussion:

1. **Title change**: current → desired.
   - Desired: `AZIP-<N>: <current title with any existing AZIP-K prefix stripped>`.
2. **Body prepend**: show the exact line to add at the top:
   - `**AZIP:** [AZIP-<N>](<pr-url>)`
   - If a stale `**AZIP:** [AZIP-K](...)` line is already at the top, replace it rather than stack.
3. **Label**: add `has-azip` to the discussion if not already present. Verify the label exists on the repo first:

```bash
gh api graphql -f query='query($o:String!,$n:String!){repository(owner:$o,name:$n){label(name:"has-azip"){id}}}' -F o=AztecProtocol -F n=governance
```

Present these as a copy-pasteable list. Do **not** apply them automatically — the editor applies them via the GitHub UI or `gh` so the audit trail is clean. (Once PR 18 lands, this whole step becomes a no-op and should be removed from the skill.)

## Step 6 — Print the changes that are needed

Output a flat, copy-pasteable list of every change required for the AZIP to pass an editor review. No PR comment template, no boilerplate scope statements — just the actionable items, grouped by where the change goes.

Suggested layout:

```
### Required changes (in `AZIPs/azip-<N>.md`)
- <change 1, with the exact line / cell / section to edit>
- <change 2>

### Required changes (PR / discussion)
- <e.g. "create discussion in azip-proposals category and update `discussions-to`">
- <e.g. "add PR description with discussion link">

### Nits (non-blocking)
- <minor formatting / whitespace items>

### Flagged for reviewers (not editor objections)
- <anything borderline-substantive that Core Contributors should weigh in on>

### Discussion sync (manual until #18 lands)
- Title → `AZIP-<N>: <stripped title>`
- Body prepend: `**AZIP:** [AZIP-<N>](<pr-url>)`
- Label: `has-azip`
```

Keep entries terse and concrete (one line each, naming the exact field/section). The editor or author decides what to do with the list; the skill doesn't pre-write a review comment for them.

If a section has no items, omit the heading rather than printing "none".

## Notes on what NOT to do

- Do **not** evaluate whether the proposal is a good idea, technically correct, or aligned with the roadmap. That is reviewer / Core Contributor territory.
- Do **not** push commits to the PR branch. Suggest changes; the author applies them.
- Do **not** mutate the discussion automatically. Hand the edits to the editor.
- Do **not** merge the PR. Even when everything checks out, the editor merges manually after confirming peer review and stakeholder engagement.
- Do **not** assign an AZIP number if one is already assigned, even if it is out of sequence — reassignment is an explicit editorial decision.

## References

- `README.md` — editor list and contributor flow.
- `azip-process.md` — full lifecycle, content requirements, editor responsibilities.
- `governance-manual.md` — broader governance context, dispute handling.
- `AZIPs/template.md` — template the preamble and sections must match.
- PR #18 (`workflow/link-azip-to-discussion`) — the automation that will replace Step 5 once merged.
