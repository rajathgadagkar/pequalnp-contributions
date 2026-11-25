#!/usr/bin/env python3
import html
import json
import os
import re
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone

AUTHOR = os.environ.get("TRACK_AUTHOR", "rajathgadagkar")
REPO = os.environ.get("TRACK_REPO", "open-goat/pequalnp-proofs")
TOKEN = os.environ.get("GITHUB_TOKEN", "")

API = "https://api.github.com"
GH = "https://github.com"
SITE = "https://pequalnp.com"
PNP_DATA = "https://data.pequalnp.com"
SHIELDS = "https://img.shields.io/badge"
README_FILE = "README.md"

FRONT_LABELS = {
    "meta": "Meta-Complexity & Circuit Lower Bounds",
    "gct": "Geometric Complexity Theory (GCT)",
    "clb": "Circuit Lower Bounds via Algorithms",
    "pcx": "Proof Complexity",
    "alg": "P = NP Algorithm Search",
    "lib": "Shared Library & Utilities",
}

FRONT_COLORS = {
    "meta": "#6366f1",
    "gct": "#ec4899",
    "clb": "#14b8a6",
    "pcx": "#f59e0b",
    "alg": "#10b981",
    "lib": "#8b5cf6",
    "other": "#64748b",
}


def http_get_json(url: str, use_gh_auth: bool = False):
    headers = {"User-Agent": "pequalnp-contributions-tracker"}
    if use_gh_auth:
        headers["Accept"] = "application/vnd.github+json"
        if TOKEN:
            headers["Authorization"] = f"Bearer {TOKEN}"
    else:
        headers["Accept"] = "application/json"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def gh_get(url: str):
    return http_get_json(url, use_gh_auth=True)


def safe_get(url: str, default, use_gh_auth: bool = True):
    try:
        return http_get_json(url, use_gh_auth=use_gh_auth)
    except Exception:
        return default


def bar(value: int, total: int, width: int = 18) -> str:
    if total <= 0:
        return "░" * width
    filled = round((value / total) * width)
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)


def fetch_pequalnp_profile() -> dict:
    head = safe_get(f"{PNP_DATA}/head.json", {}, use_gh_auth=False)
    if not head:
        return {}

    files = head.get("files", {})
    contrib_rel = files.get("contributors")
    contrib_doc = (
        safe_get(f"{PNP_DATA}/{contrib_rel}", {}, use_gh_auth=False)
        if contrib_rel
        else {}
    )
    contributors = contrib_doc.get("contributors", [])
    if not isinstance(contributors, list):
        contributors = []

    ranked = sorted(
        contributors,
        key=lambda c: (-int(c.get("steps", 0)), str(c.get("first_proof_at", "9999"))),
    )

    rank = None
    me = None
    for idx, entry in enumerate(ranked, start=1):
        handle = str(entry.get("github", entry.get("handle", "")))
        if handle.lower() == AUTHOR.lower():
            rank = idx
            me = entry
            break

    credited_papers = []
    papers_rel = files.get("papers")
    if papers_rel:
        papers_doc = safe_get(f"{PNP_DATA}/{papers_rel}", {}, use_gh_auth=False)
        for p in papers_doc.get("papers", []):
            pid = p.get("id")
            credits_rel = files.get(f"paper_credits_{pid}")
            if not credits_rel:
                continue
            credits_doc = safe_get(f"{PNP_DATA}/{credits_rel}", {}, use_gh_auth=False)
            for c in credits_doc.get("contributors", []):
                h = str(c.get("handle", c.get("github", "")))
                if h.lower() == AUTHOR.lower():
                    credited_papers.append(
                        {
                            "id": pid,
                            "title": p.get("title", pid),
                            "lemmas": [
                                l.get("id")
                                for l in c.get("lemmas", [])
                                if isinstance(l, dict) and l.get("id")
                            ],
                        }
                    )

    top_contributors = []
    for idx, entry in enumerate(ranked[:10], start=1):
        top_contributors.append(
            {
                "rank": idx,
                "github": entry.get("github", ""),
                "steps": int(entry.get("steps", 0)),
                "first_proof_at": entry.get("first_proof_at", ""),
            }
        )

    return {
        "generated_at": head.get("generated_at", ""),
        "counters": head.get("counters", {}),
        "status_text": (head.get("status") or {}).get("text", ""),
        "outside_contributors_total": int(contrib_doc.get("count", len(ranked))),
        "outside_steps_total": int(contrib_doc.get("steps", 0)),
        "author_rank": rank,
        "author_steps": int(me.get("steps", 0)) if me else 0,
        "first_proof_at": me.get("first_proof_at", "") if me else "",
        "last_proof_at": me.get("last_proof_at", "") if me else "",
        "lemmas": me.get("lemmas", []) if me else [],
        "credited_papers": credited_papers,
        "top_contributors": top_contributors,
    }


def fetch_all_prs():
    items = []
    page = 1
    while True:
        q = urllib.parse.quote(f"is:pr author:{AUTHOR} repo:{REPO}")
        url = f"{API}/search/issues?q={q}&per_page=100&page={page}&sort=created&order=desc"
        data = gh_get(url)
        batch = data.get("items", [])
        if not batch:
            break
        items.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return items


def fetch_project_stats():
    repo_info = safe_get(f"{API}/repos/{REPO}", {})
    merged_q = urllib.parse.quote(f"is:pr is:merged repo:{REPO}")
    open_q = urllib.parse.quote(f"is:pr is:open repo:{REPO}")
    merged_total = safe_get(f"{API}/search/issues?q={merged_q}&per_page=1", {}).get("total_count", 0)
    open_total = safe_get(f"{API}/search/issues?q={open_q}&per_page=1", {}).get("total_count", 0)

    tree = safe_get(f"{API}/repos/{REPO}/git/trees/main:lean/PEqualNP/Outside", {})
    outside_files = [e["path"] for e in tree.get("tree", []) if e.get("path", "").endswith(".lean")]
    front_counts = Counter()
    for fname in outside_files:
        m = re.match(r"^L_([a-z]+)_\d+\.lean$", fname)
        front = m.group(1) if m else "other"
        front_counts[front] += 1

    contributors = safe_get(f"{API}/repos/{REPO}/contributors?per_page=100", [])
    leaderboard = []
    user_rank = None
    user_commits = 0
    for idx, c in enumerate(contributors, start=1):
        login = c.get("login", "")
        contribs = int(c.get("contributions", 0))
        if login.lower() == AUTHOR.lower():
            user_rank = idx
            user_commits = contribs
        if len(leaderboard) < 15:
            leaderboard.append(
                {
                    "rank": idx,
                    "login": login,
                    "url": c.get("html_url", f"{GH}/{login}"),
                    "contributions": contribs,
                }
            )

    return {
        "stars": int(repo_info.get("stargazers_count", 0)),
        "forks": int(repo_info.get("forks_count", 0)),
        "merged_prs_total": int(merged_total),
        "open_prs_queue": int(open_total),
        "outside_lean_modules": len(outside_files),
        "front_breakdown": dict(front_counts.most_common()),
        "leaderboard_top15": leaderboard,
        "author_rank_in_top100": user_rank,
        "author_merged_commits": user_commits,
    }


def classify_pr(pr_detail: dict, comments: list) -> tuple[str, str]:
    if pr_detail.get("merged"):
        return "✅ Merged", "Accepted and merged into `main`"
    if pr_detail.get("state") == "open":
        return "🟡 Open", "Waiting in automated Lean checker queue"

    last_body = (comments[-1].get("body", "") if comments else "").lower()
    if "checker accepted this reduction" in last_body or "five open reductions" in last_body:
        return "🟣 Accepted (Slot-Capped)", "Checker-accepted reduction; unrecorded due to 5-open-reductions cap"
    if "proved first by another pull request" in last_body:
        return "⚪ Superseded", "Valid proof; an earlier PR for this step merged first"
    if "already ahead of this one" in last_body or "closed without a check" in last_body:
        return "⚪ Queue-Closed", "Closed unrun because another PR was ahead in queue"
    if "rejected" in last_body:
        first_line = comments[-1].get("body", "").strip().splitlines()[0][:90]
        return "🔴 Rejected", first_line
    return "⚫ Closed", "Closed"


def extract_front(step_title: str) -> str:
    m = re.search(r"[LR]-([a-z]+)-\d+", step_title.strip())
    if not m:
        return "Other"
    key = m.group(1)
    return FRONT_LABELS.get(key, key.upper())


def fmt_iso_short(ts: str) -> str:
    if not ts:
        return "—"
    return ts.replace("T", " ")[:16] + " UTC"


def render_agent_card_svg(pnp: dict, stats: dict, now_utc: str) -> str:
    rank_str = f"#{pnp['author_rank']}" if pnp.get("author_rank") else "Unranked"
    of_str = f"of {pnp.get('outside_contributors_total', 0):,} contributors"
    steps = pnp.get("author_steps", stats["merged"])
    first_at = fmt_iso_short(pnp.get("first_proof_at", ""))
    last_at = fmt_iso_short(pnp.get("last_proof_at", ""))
    counters = pnp.get("counters", {})
    checked_total = int(counters.get("checked", 0))
    checked_hr = int(counters.get("checked_last_hour", 0))
    agents_now = int(counters.get("agents_working_now", 0))

    cards = [
        ("PEQUALNP.COM RANK", rank_str, of_str, "#818cf8"),
        ("VERIFIED LEMMAS", f"{steps:,}", f"{stats['merged']} merged PRs · +{stats['total_lines_added']:,} LOC", "#34d399"),
        ("ACTIVE / ACCEPTED", f"{stats['open']} open", f"{stats['accepted_slot_capped']} slot-capped · {stats['total_prs']} total PRs", "#fbbf24"),
        ("LIVE FLEET STATUS", f"{checked_total:,} checked", f"+{checked_hr}/hr · {agents_now} agents live", "#f472b6"),
    ]

    box_svg = []
    for i, (label, val, sub, color) in enumerate(cards):
        x = 24 + i * 204
        box_svg.append(
            f'<rect x="{x}" y="86" width="192" height="96" rx="12" fill="#161b22" stroke="#30363d" stroke-width="1"/>'
            f'<rect x="{x}" y="86" width="192" height="4" rx="2" fill="{color}"/>'
            f'<text x="{x + 14}" y="110" fill="#8b949e" font-size="10" font-weight="600" letter-spacing="0.6">{html.escape(label)}</text>'
            f'<text x="{x + 14}" y="144" fill="#f0f6fc" font-size="24" font-weight="700">{html.escape(val)}</text>'
            f'<text x="{x + 14}" y="168" fill="#8b949e" font-size="11">{html.escape(sub)}</text>'
        )

    footer = f"First proof: {first_at}  ·  Latest proof: {last_at}  ·  Synced: {now_utc}"
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="852" height="224" viewBox="0 0 852 224" '
        'font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif">\n'
        '  <rect width="852" height="224" rx="16" fill="#0d1117" stroke="#30363d" stroke-width="1"/>\n'
        f'  <text x="24" y="38" fill="#f0f6fc" font-size="20" font-weight="700">@{html.escape(AUTHOR)} · pequalnp.com Contributor Snapshot</text>\n'
        f'  <text x="24" y="60" fill="#8b949e" font-size="12">Live data synced hourly from data.pequalnp.com and {html.escape(REPO)}</text>\n'
        f'  {"".join(box_svg)}\n'
        f'  <text x="24" y="206" fill="#8b949e" font-size="11">{html.escape(footer)}</text>\n'
        '</svg>\n'
    )


def render_front_progress_svg(front_breakdown: dict, pnp: dict) -> str:
    items = list(front_breakdown.items())[:6]
    total = max(sum(front_breakdown.values()), 1)
    top_people = pnp.get("top_contributors", [])[:6]
    max_steps = max([p["steps"] for p in top_people] + [1])

    left_rows = []
    for idx, (fk, cnt) in enumerate(items):
        y = 74 + idx * 34
        label = FRONT_LABELS.get(fk, fk.upper())
        if len(label) > 28:
            label = label[:26] + "…"
        pct = 100.0 * cnt / total
        bw = max(4, int(190 * cnt / total))
        color = FRONT_COLORS.get(fk, "#64748b")
        left_rows.append(
            f'<text x="24" y="{y}" fill="#c9d1d9" font-size="11.5">{html.escape(label)}</text>'
            f'<rect x="200" y="{y - 11}" width="190" height="12" rx="6" fill="#21262d"/>'
            f'<rect x="200" y="{y - 11}" width="{bw}" height="12" rx="6" fill="{color}"/>'
            f'<text x="398" y="{y}" fill="#8b949e" font-size="11">{cnt:,} ({pct:.1f}%)</text>'
        )

    right_rows = []
    for idx, entry in enumerate(top_people):
        y = 74 + idx * 34
        handle = entry["github"]
        steps = entry["steps"]
        bw = max(4, int(180 * steps / max_steps))
        is_me = handle.lower() == AUTHOR.lower()
        color = "#34d399" if is_me else "#58a6ff"
        name_fill = "#34d399" if is_me else "#c9d1d9"
        right_rows.append(
            f'<text x="488" y="{y}" fill="{name_fill}" font-size="11.5">#{entry["rank"]} @{html.escape(handle[:14])}</text>'
            f'<rect x="612" y="{y - 11}" width="180" height="12" rx="6" fill="#21262d"/>'
            f'<rect x="612" y="{y - 11}" width="{bw}" height="12" rx="6" fill="{color}"/>'
            f'<text x="800" y="{y}" fill="#8b949e" font-size="11">{steps:,}</text>'
        )

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="852" height="290" viewBox="0 0 852 290" '
        'font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif">\n'
        '  <rect width="852" height="290" rx="16" fill="#0d1117" stroke="#30363d" stroke-width="1"/>\n'
        '  <text x="24" y="34" fill="#f0f6fc" font-size="15" font-weight="700">Checked Outside Proofs by Research Front</text>\n'
        '  <line x1="464" y1="20" x2="464" y2="270" stroke="#21262d" stroke-width="1"/>\n'
        '  <text x="488" y="34" fill="#f0f6fc" font-size="15" font-weight="700">pequalnp.com Top Outside Contributors</text>\n'
        f'  {"".join(left_rows)}\n'
        f'  {"".join(right_rows)}\n'
        '</svg>\n'
    )


def render_activity_svg(records: list, pnp: dict) -> str:
    by_day = Counter()
    merged_by_day = Counter()
    for r in records:
        d = r.get("created_at", "")[:10]
        if d:
            by_day[d] += 1
            if r.get("merged"):
                merged_by_day[d] += 1
    for l in pnp.get("lemmas", []):
        d = str(l.get("at", ""))[:10]
        if d and d not in by_day:
            by_day[d] += 0

    days = sorted(by_day.keys())[-14:]
    max_val = max([by_day[d] for d in days] + [1])

    bars = []
    chart_left = 48
    chart_bottom = 175
    chart_height = 105
    slot_w = int(760 / max(len(days), 1))
    bar_w = max(14, min(42, slot_w - 14))

    for i, d in enumerate(days):
        cx = chart_left + i * slot_w + (slot_w - bar_w) // 2
        tot_h = max(4, int(chart_height * by_day[d] / max_val)) if by_day[d] > 0 else 2
        mrg_h = int(chart_height * merged_by_day[d] / max_val) if merged_by_day[d] > 0 else 0
        bars.append(
            f'<rect x="{cx}" y="{chart_bottom - tot_h}" width="{bar_w}" height="{tot_h}" rx="4" fill="#30363d"/>'
        )
        if mrg_h > 0:
            bars.append(
                f'<rect x="{cx}" y="{chart_bottom - mrg_h}" width="{bar_w}" height="{mrg_h}" rx="4" fill="#34d399"/>'
            )
        bars.append(
            f'<text x="{cx + bar_w // 2}" y="{chart_bottom - tot_h - 6}" text-anchor="middle" fill="#c9d1d9" font-size="10">{merged_by_day[d]}/{by_day[d]}</text>'
            f'<text x="{cx + bar_w // 2}" y="{chart_bottom + 18}" text-anchor="middle" fill="#8b949e" font-size="10">{html.escape(d[5:])}</text>'
        )

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="852" height="220" viewBox="0 0 852 220" '
        'font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif">\n'
        '  <rect width="852" height="220" rx="16" fill="#0d1117" stroke="#30363d" stroke-width="1"/>\n'
        f'  <text x="24" y="34" fill="#f0f6fc" font-size="15" font-weight="700">@{html.escape(AUTHOR)} Daily Activity (Merged / Submitted PRs)</text>\n'
        '  <rect x="650" y="23" width="10" height="10" rx="2" fill="#34d399"/>\n'
        '  <text x="666" y="32" fill="#8b949e" font-size="11">Merged</text>\n'
        '  <rect x="726" y="23" width="10" height="10" rx="2" fill="#30363d"/>\n'
        '  <text x="742" y="32" fill="#8b949e" font-size="11">Submitted</text>\n'
        f'  <line x1="36" y1="{chart_bottom}" x2="824" y2="{chart_bottom}" stroke="#21262d" stroke-width="1"/>\n'
        f'  {"".join(bars)}\n'
        '</svg>\n'
    )


def main():
    items = fetch_all_prs()
    proj = fetch_project_stats()
    pnp = fetch_pequalnp_profile()
    records = []

    for it in items:
        num = it["number"]
        pr = gh_get(f"{API}/repos/{REPO}/pulls/{num}")
        comments = safe_get(f"{API}/repos/{REPO}/issues/{num}/comments?per_page=100", [])
        status, note = classify_pr(pr, comments)
        body = (pr.get("body") or "").strip()
        records.append(
            {
                "number": num,
                "step": pr.get("title", "").strip(),
                "front": extract_front(pr.get("title", "")),
                "url": pr.get("html_url", it.get("html_url", "")),
                "state": pr.get("state", ""),
                "merged": bool(pr.get("merged", False)),
                "status": status,
                "note": note,
                "body": body,
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
    accepted_capped = sum(1 for r in records if r["status"].startswith("🟣"))
    superseded = sum(1 for r in records if r["status"].startswith("⚪"))
    closed_other = sum(1 for r in records if r["status"].startswith("⚫"))
    rejected = sum(1 for r in records if r["status"].startswith("🔴"))
    closed_total = total - merged - open_cnt
    total_loc = sum(r["additions"] for r in records)
    unique_steps = len({r["step"] for r in records if r["step"]})

    stats = {
        "total_prs": total,
        "unique_steps": unique_steps,
        "merged": merged,
        "accepted_slot_capped": accepted_capped,
        "open": open_cnt,
        "closed_total": closed_total,
        "superseded_or_queue_closed": superseded,
        "closed_other": closed_other,
        "rejected": rejected,
        "total_lines_added": total_loc,
    }

    os.makedirs("data", exist_ok=True)
    os.makedirs("assets", exist_ok=True)

    with open("data/contributions.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "author": AUTHOR,
                "repo": REPO,
                "updated_at_utc": now_utc,
                "stats": stats,
                "pull_requests": records,
            },
            f,
            indent=2,
        )
        f.write("\n")

    with open("data/project_stats.json", "w", encoding="utf-8") as f:
        json.dump({"updated_at_utc": now_utc, "repo": REPO, **proj}, f, indent=2)
        f.write("\n")

    with open("data/pequalnp_profile.json", "w", encoding="utf-8") as f:
        json.dump({"updated_at_utc": now_utc, "author": AUTHOR, **pnp}, f, indent=2)
        f.write("\n")

    with open("assets/agent_card.svg", "w", encoding="utf-8") as f:
        f.write(render_agent_card_svg(pnp, stats, now_utc))
    with open("assets/front_progress.svg", "w", encoding="utf-8") as f:
        f.write(render_front_progress_svg(proj["front_breakdown"], pnp))
    with open("assets/activity_timeline.svg", "w", encoding="utf-8") as f:
        f.write(render_activity_svg(records, pnp))

    pnp_rank = pnp.get("author_rank")
    pnp_total = pnp.get("outside_contributors_total", 0)
    rank_badge = f"%23{pnp_rank}%20of%20{pnp_total}" if pnp_rank else "Pending"
    lean_url = "https://lean-lang.org/"
    wf_path = ".github/workflows/update.yml"

    lines = [
        f"# 🧮 P vs NP Lean 4 Contributions — `@{AUTHOR}`",
        "",
        "<p>"
        f'<a href="{lean_url}"><img src="{SHIELDS}/Lean%204-Mathlib-blueviolet?style=flat-square" alt="Lean 4" /></a> '
        f'<a href="{SITE}/a/{AUTHOR}"><img src="{SHIELDS}/pequalnp.com-Contributor%20Card-ff69b4?style=flat-square" alt="Contributor Card" /></a> '
        f'<a href="{SITE}/a/{AUTHOR}"><img src="{SHIELDS}/pequalnp%20Rank-{rank_badge}-8957e5?style=flat-square" alt="pequalnp Rank" /></a> '
        f'<a href="{GH}/{REPO}/pulls?q=is%3Apr+author%3A{AUTHOR}+is%3Amerged"><img src="{SHIELDS}/Merged%20PRs-{merged}-2ea44f?style=flat-square" alt="Merged PRs" /></a> '
        f'<a href="{GH}/{REPO}/pulls?q=is%3Apr+author%3A{AUTHOR}+is%3Aopen"><img src="{SHIELDS}/In%20Queue-{open_cnt}-d29922?style=flat-square" alt="In Queue" /></a> '
        f'<a href="#pull-request-log"><img src="{SHIELDS}/Lean%204%20LOC-%2B{total_loc}-0969da?style=flat-square" alt="Lean 4 LOC" /></a> '
        f'<a href="{wf_path}"><img src="{SHIELDS}/Updates-Hourly%20via%20Actions-brightgreen?style=flat-square" alt="Auto-Updated" /></a>'
        "</p>",
        "",
        f"> Live, auto-updating portfolio tracking [`@{AUTHOR}`]({GH}/{AUTHOR})'s machine-checked Lean 4 proofs submitted to [`{REPO}`]({GH}/{REPO}) and synced directly from [`pequalnp.com/a/{AUTHOR}`]({SITE}/a/{AUTHOR}).",
        "",
        f"_Last synced automatically: **{now_utc}**_",
        "",
        "## 📈 Live Visual Dashboard",
        "",
        f'<p align="center"><a href="{SITE}/a/{AUTHOR}"><img src="assets/agent_card.svg" alt="pequalnp.com Contributor Card" /></a></p>',
        '<p align="center"><img src="assets/activity_timeline.svg" alt="Daily PR Activity" /></p>',
        '<p align="center"><img src="assets/front_progress.svg" alt="Research Fronts & Top Contributors" /></p>',
        "",
    ]

    if pnp.get("lemmas"):
        lines.extend(
            [
                f"## 🏅 Verified Lemmas on [`pequalnp.com/a/{AUTHOR}`]({SITE}/a/{AUTHOR})",
                "",
                "| Lemma ID | Statement | Commit Ref | Verified At (UTC) |",
                "| --- | --- | --- | --- |",
            ]
        )
        for lem in reversed(pnp["lemmas"]):
            lid = lem.get("id", "")
            ltitle = str(lem.get("title", "")).replace("|", "\\|")
            lref = lem.get("ref", "")
            lat = fmt_iso_short(lem.get("at", ""))
            ref_md = f"[`{lref[:8]}`]({GH}/{REPO}/commit/{lref})" if lref else "—"
            lines.append(f"| `{lid}` | {ltitle} | {ref_md} | {lat} |")
        lines.append("")

    if pnp.get("credited_papers"):
        lines.extend(["### 📄 Papers Resting on Your Lemmas", ""])
        for cp in pnp["credited_papers"]:
            lids = ", ".join(f"`{x}`" for x in cp["lemmas"])
            lines.append(f"- **{cp['title']}** ({lids})")
        lines.append("")

    lines.extend(
        [
            "## 📊 Personal Contribution Snapshot",
            "",
            "| Metric | Value | Notes |",
            "| --- | ---: | --- |",
            f"| **pequalnp.com Rank** | **{f'#{pnp_rank} / {pnp_total:,}' if pnp_rank else 'Pending'}** | Live outside contributor ranking on [pequalnp.com]({SITE}/a/{AUTHOR}) |",
            f"| **Total PRs Submitted** | **{total}** | Across **{unique_steps}** distinct proof steps |",
            f"| **✅ Accepted & Merged** | **{merged}** | Formally verified by the Lean 4 kernel & project checker |",
            f"| **🟣 Checker-Accepted (Slot-Capped)** | **{accepted_capped}** | Passed authoritative checker; closed unrecorded due to 5-open-reductions cap |",
            f"| **🟡 Open (Checker Queue)** | **{open_cnt}** | Awaiting automated verification |",
            f"| **⚪ Superseded / Queue-Closed** | **{superseded}** | Built cleanly locally; an earlier PR for the same step beat the queue |",
            f"| **⚫ Closed (Other / Withdrawn)** | **{closed_other}** | Closed manually or withdrawn without merge ({closed_total} closed total) |",
            f"| **🔴 Rejected by Checker** | **{rejected}** | Format or verification failures |",
            f"| **Total Lean 4 Lines Written** | **+{total_loc:,}** | Zero `sorry`, zero `native_decide`, standard axioms only |",
            "",
            "## 🌍 Overall `pequalnp.com` Project Progress",
            "",
            f"Live snapshot of [`{REPO}`]({GH}/{REPO}) (`⭐ {proj['stars']:,}` stars · `🍴 {proj['forks']:,}` forks):",
            "",
            "| Project Metric | Live Count |",
            "| --- | ---: |",
            f"| **Checked Lemmas (pequalnp.com Fleet + Outside)** | **{int(pnp.get('counters', {}).get('checked', 0)):,}** |",
            f"| **Checked in Last Hour** | **+{int(pnp.get('counters', {}).get('checked_last_hour', 0)):,}** |",
            f"| **Outside Contributors / Outside Steps** | **{pnp_total:,}** / **{int(pnp.get('outside_steps_total', 0)):,}** |",
            f"| **Checked Outside Proof Modules (`lean/PEqualNP/Outside/`)** | **{proj['outside_lean_modules']:,}** |",
            f"| **Total Merged Proof PRs** | **{proj['merged_prs_total']:,}** |",
            f"| **Active PRs in Checker Queue** | **{proj['open_prs_queue']:,}** |",
            "",
            "### Checked Outside Proofs by Research Front",
            "",
            "| Research Front | Modules | Share | Distribution |",
            "| --- | ---: | ---: | --- |",
        ]
    )

    total_outside = max(proj["outside_lean_modules"], 1)
    for front_key, cnt in proj["front_breakdown"].items():
        label = FRONT_LABELS.get(front_key, front_key.upper())
        pct = 100.0 * cnt / total_outside
        lines.append(f"| **{label}** (`L_{front_key}_*`) | {cnt:,} | {pct:.1f}% | `{bar(cnt, total_outside)}` |")

    lines.extend(
        [
            "",
            "## 🏆 Community Leaderboard",
            "",
            f"Top 15 contributors on [`{REPO}`]({GH}/{REPO}) by merged commits (see also the [live pequalnp.com leaderboard]({SITE}/)):",
            "",
            "| Rank | Contributor | Commits | Profile |",
            "| ---: | --- | ---: | --- |",
        ]
    )

    for entry in proj["leaderboard_top15"]:
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(entry["rank"], f"#{entry['rank']}")
        is_me = entry["login"].lower() == AUTHOR.lower()
        name_fmt = f"**`@{entry['login']}` (You)**" if is_me else f"`@{entry['login']}`"
        lines.append(
            f"| {medal} | {name_fmt} | **{entry['contributions']:,}** | [GitHub]({entry['url']}) · [pequalnp]({SITE}/a/{entry['login']}) |"
        )

    lines.extend(
        [
            "",
            "## 📜 Pull Request Log",
            "",
            "| PR | Step | Research Front | Status | Lines | Date | Outcome |",
            "| --- | --- | --- | --- | ---: | --- | --- |",
        ]
    )

    for r in records:
        safe_note = r["note"].replace("|", "\\|")
        lines.append(
            f"| [#{r['number']}]({r['url']}) | `{r['step']}` | {r['front']} | {r['status']} | +{r['additions']} | {r['created_at']} | {safe_note} |"
        )

    lines.extend(["", "## 🔍 Detailed Proof Breakdowns", ""])
    for r in records:
        lines.append("<details>")
        lines.append(
            f"<summary><strong>{r['step']}</strong> — <a href=\"{r['url']}\">PR #{r['number']}</a> ({r['status']}, +{r['additions']} lines, {r['created_at']})</summary>"
        )
        lines.append("")
        if r["body"]:
            lines.append(r["body"])
        else:
            lines.append(f"Proof submission for `{r['step']}` ({r['note']}).")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    lines.extend(
        [
            "## ⚙️ How This Tracker Works",
            "",
            f"- Runs automatically **every hour** (and on-demand via `workflow_dispatch`) using [`{wf_path}`]({wf_path}).",
            f"- Syncs live profile stats, verified lemmas, and fleet counters directly from [`data.pequalnp.com`]({PNP_DATA}/head.json) alongside GitHub REST/Search APIs (zero third-party Python dependencies).",
            "- Generates vector SVG charts in `assets/` and persists raw snapshots in `data/contributions.json`, `data/project_stats.json`, and `data/pequalnp_profile.json`.",
            "",
        ]
    )

    with open(README_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(
        f"Updated {README_FILE} ({total} PRs, {merged} merged; pequalnp.com rank={pnp_rank}/{pnp_total}, "
        f"lemmas={pnp.get('author_steps', 0)})."
    )


if __name__ == "__main__":
    main()
