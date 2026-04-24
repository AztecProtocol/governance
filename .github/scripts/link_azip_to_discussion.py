#!/usr/bin/env python3
"""Link an AZIP PR to its GitHub Discussion.

Reads the AZIP markdown files changed in a PR, parses the preamble table to
extract the AZIP number and `discussions-to` URL, then updates the target
discussion to:

    * carry a `has-azip` label
    * have the AZIP PR linked at the top of its body
    * be titled `AZIP-N: <original title>`

All mutations are idempotent: re-running makes no change when the discussion
is already linked.

Expected environment:
    GH_TOKEN    GitHub token with `discussions: write` and `pull-requests: read`.
    REPO        owner/name of the repo (e.g. "AztecProtocol/governance").
    PR_NUMBER   Pull request number.
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
from typing import Any

REPO = os.environ["REPO"]
PR_NUMBER = int(os.environ["PR_NUMBER"])
OWNER, REPO_NAME = REPO.split("/", 1)

# Strict: AZIP discussions must live in this exact repo, and in this category.
DISCUSSION_URL_RE = re.compile(
    rf"^https://github\.com/{re.escape(OWNER)}/{re.escape(REPO_NAME)}/discussions/(\d+)/?$"
)
AZIP_NUM_RE = re.compile(r"^\d+$")
LABEL_NAME = "has-azip"
REQUIRED_CATEGORY_SLUG = "azip-proposals"


def gh(args: list[str], *, input_data: str | None = None) -> str:
    result = subprocess.run(
        ["gh"] + args,
        check=True,
        capture_output=True,
        text=True,
        input=input_data,
    )
    return result.stdout


def gh_json(args: list[str]) -> Any:
    out = gh(args)
    return json.loads(out) if out.strip() else None


def graphql(query: str, variables: dict[str, Any]) -> dict[str, Any]:
    payload = json.dumps({"query": query, "variables": variables})
    out = gh(["api", "graphql", "--input", "-"], input_data=payload)
    data = json.loads(out)
    if "errors" in data and data["errors"]:
        raise RuntimeError(f"GraphQL errors: {data['errors']}")
    return data["data"]


def get_pr() -> dict[str, Any]:
    return gh_json(["api", f"repos/{REPO}/pulls/{PR_NUMBER}"])


def list_changed_azips(head_sha: str) -> list[str]:
    files = gh_json(["api", "--paginate", f"repos/{REPO}/pulls/{PR_NUMBER}/files"])
    changed: list[str] = []
    for f in files:
        name = f["filename"]
        if not name.startswith("AZIPs/") or not name.endswith(".md"):
            continue
        if name == "AZIPs/template.md":
            continue
        if f.get("status") == "removed":
            continue
        changed.append(name)
    return changed


def fetch_file_at_ref(path: str, ref: str) -> str:
    import urllib.parse

    encoded = urllib.parse.quote(path)
    data = gh_json(["api", f"repos/{REPO}/contents/{encoded}?ref={ref}"])
    if data.get("encoding") != "base64":
        raise RuntimeError(f"Unexpected encoding for {path}: {data.get('encoding')!r}")
    return base64.b64decode(data["content"]).decode("utf-8")


def split_row(row: str) -> list[str]:
    row = row.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|"):
        row = row[:-1]
    return [cell.strip() for cell in row.split("|")]


def parse_preamble(md: str) -> dict[str, str]:
    """Parse the AZIP preamble table.

    The preamble is a two-row markdown table whose header cells are wrapped
    in backticks (e.g. `` `azip` ``). Returns a dict keyed by the unwrapped
    header name, mapped to the corresponding cell in the single data row.
    """
    lines = md.split("\n")
    for i, line in enumerate(lines):
        if "`azip`" in line and "`discussions-to`" in line:
            if i + 2 >= len(lines):
                raise ValueError("preamble table truncated")
            headers = [h.strip().strip("`") for h in split_row(lines[i])]
            data = split_row(lines[i + 2])
            if len(data) != len(headers):
                raise ValueError(
                    f"preamble header/data mismatch: {len(headers)} vs {len(data)}"
                )
            return dict(zip(headers, data))
    raise ValueError("preamble header row not found")


def ensure_label_id() -> str:
    data = graphql(
        """
        query($owner: String!, $name: String!, $label: String!) {
          repository(owner: $owner, name: $name) {
            label(name: $label) { id }
          }
        }
        """,
        {"owner": OWNER, "name": REPO_NAME, "label": LABEL_NAME},
    )
    label = data["repository"]["label"]
    if label:
        return label["id"]
    raise RuntimeError(
        f"Label {LABEL_NAME!r} does not exist on {REPO}. "
        "Create it once (Issues → Labels) before running this workflow."
    )


def get_discussion(number: int) -> dict[str, Any]:
    data = graphql(
        """
        query($owner: String!, $name: String!, $number: Int!) {
          repository(owner: $owner, name: $name) {
            discussion(number: $number) {
              id
              title
              body
              category { slug name }
              labels(first: 50) { nodes { name } }
            }
          }
        }
        """,
        {"owner": OWNER, "name": REPO_NAME, "number": number},
    )
    disc = data["repository"]["discussion"]
    if not disc:
        raise RuntimeError(f"Discussion #{number} not found")
    slug = (disc.get("category") or {}).get("slug")
    if slug != REQUIRED_CATEGORY_SLUG:
        raise RuntimeError(
            f"Discussion #{number} is in category {slug!r}; refusing to mutate. "
            f"Only {REQUIRED_CATEGORY_SLUG!r} discussions may be linked to AZIPs."
        )
    return disc


def add_label(discussion_id: str, label_id: str) -> None:
    graphql(
        """
        mutation($id: ID!, $labels: [ID!]!) {
          addLabelsToLabelable(input: { labelableId: $id, labelIds: $labels }) {
            clientMutationId
          }
        }
        """,
        {"id": discussion_id, "labels": [label_id]},
    )


def update_discussion(discussion_id: str, *, title: str, body: str) -> None:
    graphql(
        """
        mutation($id: ID!, $title: String!, $body: String!) {
          updateDiscussion(input: { discussionId: $id, title: $title, body: $body }) {
            discussion { id }
          }
        }
        """,
        {"id": discussion_id, "title": title, "body": body},
    )


def desired_title(current_title: str, azip_num: int) -> str:
    # Strip any leading `AZIP-\d+` prefix (regardless of the specific number)
    # so title normalization stays idempotent even when the AZIP number is
    # reassigned mid-review. Also tolerates zero padding, and `:`/`-`/space
    # separators after the number.
    prefix_re = re.compile(r"^AZIP-\d+\s*[:\-]?\s*", re.IGNORECASE)
    stripped = prefix_re.sub("", current_title).strip()
    return f"AZIP-{azip_num}: {stripped}"


def desired_body(current_body: str, azip_num: int, pr_url: str) -> str:
    link_line = f"**AZIP:** [AZIP-{azip_num}]({pr_url})"
    # If an AZIP link block already exists at the top, replace it rather than stacking.
    existing = re.match(
        r"^\*\*AZIP:\*\*\s*\[AZIP-\d+\]\(https?://\S+\)\s*\n+",
        current_body,
    )
    rest = current_body[existing.end():] if existing else current_body.lstrip("\n")
    return f"{link_line}\n\n{rest}"


def process_azip(path: str, pr_url: str, head_sha: str, label_id: str) -> None:
    print(f"::group::{path}")
    try:
        md = fetch_file_at_ref(path, head_sha)
        preamble = parse_preamble(md)

        azip_raw = preamble.get("azip", "").strip()
        disc_raw = preamble.get("discussions-to", "").strip()

        if not AZIP_NUM_RE.match(azip_raw):
            print(f"::notice file={path}::azip number not yet assigned ({azip_raw!r}); skipping")
            return

        m = DISCUSSION_URL_RE.match(disc_raw)
        if not m:
            print(
                f"::warning file={path}::discussions-to is not a "
                f"{OWNER}/{REPO_NAME} discussion URL ({disc_raw!r}); skipping"
            )
            return

        azip_num = int(azip_raw)
        disc_num = int(m.group(1))

        disc = get_discussion(disc_num)
        new_title = desired_title(disc["title"], azip_num)
        new_body = desired_body(disc["body"], azip_num, pr_url)

        title_changed = new_title != disc["title"]
        body_changed = new_body != disc["body"]
        has_label = any(l["name"] == LABEL_NAME for l in disc["labels"]["nodes"])

        if not has_label:
            add_label(disc["id"], label_id)
            print(f"Added label {LABEL_NAME!r} to discussion #{disc_num}")
        else:
            print(f"Label {LABEL_NAME!r} already present on discussion #{disc_num}")

        if title_changed or body_changed:
            update_discussion(disc["id"], title=new_title, body=new_body)
            parts = []
            if title_changed:
                parts.append("title")
            if body_changed:
                parts.append("body")
            print(f"Updated discussion #{disc_num} ({', '.join(parts)})")
        else:
            print(f"Discussion #{disc_num} already linked; no body/title change")
    finally:
        print("::endgroup::")


def main() -> int:
    pr = get_pr()
    pr_url = pr["html_url"]
    head_sha = pr["head"]["sha"]

    files = list_changed_azips(head_sha)
    if not files:
        print("No AZIP files changed in this PR; nothing to do.")
        return 0

    label_id = ensure_label_id()

    # Guard: two changed AZIPs must not target the same discussion. Last
    # writer would win otherwise, silently.
    seen_discussions: dict[int, str] = {}
    errors = 0
    for path in files:
        try:
            md = fetch_file_at_ref(path, head_sha)
            preamble = parse_preamble(md)
            disc_raw = preamble.get("discussions-to", "").strip()
            m = DISCUSSION_URL_RE.match(disc_raw)
            if m:
                disc_num = int(m.group(1))
                if disc_num in seen_discussions:
                    print(
                        f"::error file={path}::discussion #{disc_num} is also "
                        f"referenced by {seen_discussions[disc_num]}; refusing "
                        f"to mutate the same discussion twice in one run"
                    )
                    errors += 1
                    continue
                seen_discussions[disc_num] = path
            process_azip(path, pr_url, head_sha, label_id)
        except Exception as e:
            print(f"::error file={path}::{e}")
            errors += 1
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
