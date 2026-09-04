#!/usr/bin/env python3
import json
import os
import urllib.request
from collections import defaultdict
from html import escape
from pathlib import Path

LOGIN = os.environ.get("GITHUB_LOGIN", "TheSilentD3ath")
TOKEN = os.environ["GH_TOKEN"]
OUT_DIR = Path("profile")
OUT_DIR.mkdir(parents=True, exist_ok=True)

GRAPHQL_URL = "https://api.github.com/graphql"
QUERY = r'''
query($login: String!) {
  user(login: $login) {
    name
    login
    followers { totalCount }
    contributionsCollection {
      contributionCalendar { totalContributions }
    }
    repositories(
      first: 100
      ownerAffiliations: OWNER
      privacy: PUBLIC
      orderBy: {field: UPDATED_AT, direction: DESC}
    ) {
      totalCount
      nodes {
        isFork
        stargazerCount
        forkCount
        languages(first: 20, orderBy: {field: SIZE, direction: DESC}) {
          edges {
            size
            node { name color }
          }
        }
      }
    }
  }
}
'''


def graphql(query, variables):
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "TheSilentD3ath-profile-stats",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        data = json.load(response)
    if data.get("errors"):
        raise RuntimeError(json.dumps(data["errors"], indent=2))
    return data["data"]


def fmt_number(value):
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}k"
    return str(value)


def svg_header(width, height):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">
<style>
  .title {{ fill: #70a5fd; font: 600 18px -apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif; }}
  .label {{ fill: #a9b1d6; font: 14px -apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif; }}
  .value {{ fill: #c0caf5; font: 600 15px -apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif; }}
  .small {{ fill: #a9b1d6; font: 12px -apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif; }}
</style>
<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="6" fill="#1a1b27" stroke="#30363d"/>
'''


def render_stats(user):
    repos = user["repositories"]
    own_repos = [repo for repo in repos["nodes"] if not repo["isFork"]]
    stars = sum(repo["stargazerCount"] for repo in own_repos)
    forks = sum(repo["forkCount"] for repo in own_repos)
    contributions = user["contributionsCollection"]["contributionCalendar"]["totalContributions"]
    followers = user["followers"]["totalCount"]

    width, height = 495, 195
    parts = [svg_header(width, height)]
    parts.append(f'<text x="25" y="35" class="title">{escape(LOGIN)}\'s GitHub Stats</text>')

    rows = [
        ("Contributions this year", fmt_number(contributions), 70),
        ("Public repositories", fmt_number(repos["totalCount"]), 100),
        ("Total stars", fmt_number(stars), 130),
        ("Total forks", fmt_number(forks), 160),
        ("Followers", fmt_number(followers), 190),
    ]

    # Fit five rows by using tighter spacing at the bottom.
    ys = [68, 96, 124, 152, 178]
    for (label, value, _), y in zip(rows, ys):
        parts.append(f'<text x="25" y="{y}" class="label">{escape(label)}</text>')
        parts.append(f'<text x="455" y="{y}" text-anchor="end" class="value">{escape(value)}</text>')

    parts.append("</svg>\n")
    return "\n".join(parts)


def render_languages(user):
    totals = defaultdict(int)
    colors = {}

    for repo in user["repositories"]["nodes"]:
        if repo["isFork"]:
            continue
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            totals[name] += edge["size"]
            if edge["node"].get("color"):
                colors[name] = edge["node"]["color"]

    top = sorted(totals.items(), key=lambda item: item[1], reverse=True)[:6]
    total = sum(value for _, value in top) or 1

    width, height = 495, 220
    parts = [svg_header(width, height)]
    parts.append('<text x="25" y="35" class="title">Most Used Languages</text>')

    if not top:
        parts.append('<text x="25" y="85" class="label">No public language data available yet.</text>')
        parts.append("</svg>\n")
        return "\n".join(parts)

    # Stacked percentage bar.
    x, y, bar_w, bar_h = 25.0, 55, 445.0, 10
    current_x = x
    for name, value in top:
        segment = bar_w * value / total
        color = colors.get(name, "#7aa2f7")
        parts.append(
            f'<rect x="{current_x:.2f}" y="{y}" width="{segment:.2f}" height="{bar_h}" fill="{escape(color)}"/>'
        )
        current_x += segment

    for index, (name, value) in enumerate(top):
        col = index % 2
        row = index // 2
        base_x = 25 + col * 235
        base_y = 95 + row * 38
        pct = value / total * 100
        color = colors.get(name, "#7aa2f7")
        parts.append(f'<circle cx="{base_x + 5}" cy="{base_y - 5}" r="5" fill="{escape(color)}"/>')
        parts.append(f'<text x="{base_x + 18}" y="{base_y}" class="label">{escape(name)}</text>')
        parts.append(f'<text x="{base_x + 210}" y="{base_y}" text-anchor="end" class="small">{pct:.1f}%</text>')

    parts.append("</svg>\n")
    return "\n".join(parts)


def main():
    data = graphql(QUERY, {"login": LOGIN})
    user = data.get("user")
    if not user:
        raise RuntimeError(f"GitHub user {LOGIN!r} was not found")

    (OUT_DIR / "stats.svg").write_text(render_stats(user), encoding="utf-8")
    (OUT_DIR / "top-langs.svg").write_text(render_languages(user), encoding="utf-8")
    print("Updated profile/stats.svg and profile/top-langs.svg")


if __name__ == "__main__":
    main()
