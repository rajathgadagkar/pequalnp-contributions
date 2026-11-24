#!/usr/bin/env python3
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone

AUTHOR = os.environ.get("TRACK_AUTHOR", "rajathgadagkar")
REPO = os.environ.get("TRACK_REPO", "open-goat/pequalnp-proofs")
TOKEN = os.environ.get("GITHUB_TOKEN", "")


def gh_get(url: str):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "pequalnp-contributions-tracker",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_all_prs():
    items = []
    page = 1
    while True:
        q = urllib.parse.quote(f"is:pr author:{AUTHOR} repo:{REPO}")
        url = f"https://api.github.com/search/issues?q={q}&per_page=100&page={page}&sort=created&order=desc"
        data = gh_get(url)
        batch = data.get("items", [])
        if not batch:
            break
        items.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return items


def classify_pr(pr_detail: dict, comments: list) -> tuple[str, str]:
    if pr_detail.get("merged"):
        return "✅ Merged", "Accepted and merged"
    if pr_detail.get("state") == "open":
        return "🟡 Open", "Waiting in checker queue"

    last_body = (comments[-1].get("body", "") if comments else "").lower()
    if "proved first by another pull request" in last_body:
        return "⚪ Superseded", "Another PR for this step merged first"
    if "already ahead of this one" in last_body or "closed without a check" in last_body:
        return "⚪ Queue-Closed", "Another PR was ahead in queue (no fault in proof)"
    if "rejected" in last_body:
        first_line = comments[-1].get("body", "").strip().splitlines()[0][:80]
        return "🔴 Rejected", first_line
    return "⚫ Closed", "Closed"


def main():
    items = fetch_all_prs()
    records = []

    for it in items:
        num = it["number"]
        pr = gh_get(f"https://api.github.com/repos/{REPO}/pulls/{num}")
        comments = gh_get(f"https://api.github.com/repos/{REPO}/issues/{num}/comments?per_page=100")
        status, note = classify_pr(pr, comments)
        records.append(
            {
                "number": num,
                "step": pr.get("title", "").strip(),
                "url": pr.get("html_url", it.get("html_url", "")),
                "state": pr.get("state", ""),
                "merged": bool(pr.get("merged", False)),
                "status": status,
                "note": note,
                "additions": int(pr.get("additions", 0)),
                "deletions": int(pr.get("deletions", 0)),
                "created_at": pr.get("created_at", "")[:10],
                "updated_at": pr.get("updated_at", "")[:10],
            }
        )

    records.sort(key=lambda r: r["number"], reverse=True)

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    total = len(records)
    merged = sum(1 for r in records if r["merged"])
    open_cnt = sum(1 for r in records if r["state"] == "open")
    superseded = sum(1 for r in records if r["status"].startswith("⚪"))
    total_loc = sum(r["additions"] for r in records)

    os.makedirs("data", exist_ok=True)
    with open("data/contributions.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "author": AUTHOR,
                "repo": REPO,
                "updated_at_utc": now_utc,
                "stats": {
                    "total_prs": total,
                    "merged": merged,
                    "open": open_cnt,
                    "superseded_or_queue_closed": superseded,
                    "total_lines_added": total_loc,
                },
                "pull_requests": records,
            },
            f,
            indent=2,
        )
        f.write("\n")

    lines = [
        f"# P vs NP Lean 4 Contributions (`{AUTHOR}`)",
        "",
        f"Automated tracker for [`@{AUTHOR}`](https://github.com/{AUTHOR})'s Lean 4 proof contributions to [`{REPO}`](https://github.com/{REPO}) ([pequalnp.com contributor page](https://pequalnp.com/a/{AUTHOR})).",
        "",
        f"_Last updated automatically: **{now_utc}**_",
        "",
        "## Summary",
        "",
        "| Metric | Count |",
        "| --- | ---: |",
        f"| Total PRs | **{total}** |",
        f"| ✅ Merged | **{merged}** |",
        f"| 🟡 Open (in queue) | **{open_cnt}** |",
        f"| ⚪ Superseded / Queue-Closed | **{superseded}** |",
        f"| Total Lean Lines Added | **+{total_loc:,}** |",
        "",
        "## Pull Requests",
        "",
        "| PR | Step | Status | Lines | Date | Outcome |",
        "| --- | --- | --- | ---: | --- | --- |",
    ]

    for r in records:
        safe_note = r["note"].replace("|", "\\|")
        lines.append(
            f"| [#{r['number']}]({r['url']}) | `{r['step']}` | {r['status']} | +{r['additions']} | {r['created_at']} | {safe_note} |"
        )

    lines.extend(
        [
            "",
            "This repository updates automatically every hour via GitHub Actions (`.github/workflows/update.yml`).",
            "",
        ]
    )

    with open("README.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Updated README.md and data/contributions.json ({total} PRs: {merged} merged, {open_cnt} open).")


if __name__ == "__main__":
    main()
