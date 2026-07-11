#!/usr/bin/env python3
"""
Generate self-hosted GitHub profile stat cards (SVG).
No third-party card services involved - data comes straight from the
GitHub GraphQL API, rendering is done right here.

Env vars:
  GITHUB_TOKEN  - provided automatically inside GitHub Actions
  GH_LOGIN      - GitHub username (default: Sissighn)
  TEST_MODE=1   - render with sample data, no API calls
"""

import datetime as dt
import json
import os
import sys
import urllib.request

# ---------------------------------------------------------------- palette --
BG = "#0d1117"
CARD_TEXT = "#c9d1d9"
MUTED = "#8b949e"
PINK = "#d16ba5"
PINK_BRIGHT = "#ff6ec7"
PERIWINKLE = "#86a8e7"
TEAL = "#2dd4bf"
YELLOW = "#f0b429"
FONT = "'Segoe UI', Ubuntu, Sans-Serif"

OUT_DIR = os.environ.get("OUT_DIR", "assets")
LOGIN = os.environ.get("GH_LOGIN", "Sissighn")


# ------------------------------------------------------------------- data --
QUERY = """
query($login: String!) {
  user(login: $login) {
    name
    followers { totalCount }
    pullRequests { totalCount }
    issues { totalCount }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestReviewContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {
      totalCount
      nodes {
        stargazerCount
        languages(first: 8, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""


def fetch_data():
    token = os.environ["GITHUB_TOKEN"]
    body = json.dumps({"query": QUERY, "variables": {"login": LOGIN}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "profile-card-generator",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    if "errors" in payload:
        raise RuntimeError(payload["errors"])
    return payload["data"]["user"]


def sample_data():
    """Fake data for local testing."""
    today = dt.date.today()
    days = []
    import random

    random.seed(7)
    for i in range(365, -1, -1):
        d = today - dt.timedelta(days=i)
        days.append(
            {"date": d.isoformat(), "contributionCount": random.choice([0, 1, 2, 3, 5, 8]) if random.random() > 0.15 else 0}
        )
    # force a live current streak
    for day in days[-12:]:
        day["contributionCount"] = max(1, day["contributionCount"])
    weeks = [{"contributionDays": days[i : i + 7]} for i in range(0, len(days), 7)]
    return {
        "name": "Sissi",
        "followers": {"totalCount": 2},
        "pullRequests": {"totalCount": 87},
        "issues": {"totalCount": 34},
        "contributionsCollection": {
            "totalCommitContributions": 812,
            "totalPullRequestReviewContributions": 23,
            "contributionCalendar": {
                "totalContributions": 1043,
                "weeks": weeks,
            },
        },
        "repositories": {
            "totalCount": 12,
            "nodes": [
                {
                    "stargazerCount": 2,
                    "languages": {
                        "edges": [
                            {"size": 52000, "node": {"name": "Python", "color": "#3572A5"}},
                            {"size": 31000, "node": {"name": "Java", "color": "#b07219"}},
                        ]
                    },
                },
                {
                    "stargazerCount": 1,
                    "languages": {
                        "edges": [
                            {"size": 48000, "node": {"name": "TypeScript", "color": "#3178c6"}},
                            {"size": 22000, "node": {"name": "JavaScript", "color": "#f1e05a"}},
                            {"size": 9000, "node": {"name": "CSS", "color": "#563d7c"}},
                        ]
                    },
                },
                {
                    "stargazerCount": 0,
                    "languages": {
                        "edges": [
                            {"size": 30000, "node": {"name": "C++", "color": "#f34b7d"}},
                            {"size": 5000, "node": {"name": "HTML", "color": "#e34c26"}},
                        ]
                    },
                },
            ],
        },
    }


# -------------------------------------------------------------- analytics --
def compute(user):
    cal = user["contributionsCollection"]["contributionCalendar"]
    days = [d for w in cal["weeks"] for d in w["contributionDays"]]
    days.sort(key=lambda d: d["date"])

    # streaks over the past year
    longest = cur = 0
    longest_run = 0
    for d in days:
        if d["contributionCount"] > 0:
            cur += 1
            longest_run = max(longest_run, cur)
        else:
            cur = 0
    # current streak: count back from today; today may still be 0
    current = 0
    for d in reversed(days):
        if d["contributionCount"] > 0:
            current += 1
        elif d["date"] == days[-1]["date"]:
            continue  # today without commits doesn't break the streak yet
        else:
            break

    stars = sum(r["stargazerCount"] for r in user["repositories"]["nodes"])

    langs = {}
    for repo in user["repositories"]["nodes"]:
        for e in repo["languages"]["edges"]:
            n = e["node"]["name"]
            langs.setdefault(n, {"size": 0, "color": e["node"]["color"] or MUTED})
            langs[n]["size"] += e["size"]
    top = sorted(langs.items(), key=lambda kv: kv[1]["size"], reverse=True)[:6]
    total_size = sum(v["size"] for _, v in top) or 1
    top = [(name, v["color"], v["size"] / total_size) for name, (v) in
           [(n, d) for n, d in top]]

    return {
        "name": user["name"] or LOGIN,
        "total_contrib": cal["totalContributions"],
        "commits": user["contributionsCollection"]["totalCommitContributions"],
        "reviews": user["contributionsCollection"]["totalPullRequestReviewContributions"],
        "prs": user["pullRequests"]["totalCount"],
        "issues": user["issues"]["totalCount"],
        "followers": user["followers"]["totalCount"],
        "repos": user["repositories"]["totalCount"],
        "stars": stars,
        "current_streak": current,
        "longest_streak": longest_run,
        "langs": top,
        "active_days": sum(1 for d in days if d["contributionCount"] > 0),
    }


# -------------------------------------------------------------- rendering --
def svg_header(w, h, title):
    return f"""<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" fill="none"
     xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{title}">
  <style>
    .title {{ font: 600 17px {FONT}; fill: {PINK}; }}
    .label {{ font: 400 13px {FONT}; fill: {CARD_TEXT}; }}
    .muted {{ font: 400 11px {FONT}; fill: {MUTED}; }}
    .value {{ font: 700 14px {FONT}; fill: {PINK_BRIGHT}; }}
    .big   {{ font: 800 34px {FONT}; fill: #ffffff; }}
    .mid   {{ font: 800 26px {FONT}; fill: #ffffff; }}
    .fadein {{ opacity: 0; animation: fade .6s ease forwards; }}
    @keyframes fade {{ to {{ opacity: 1; }} }}
    @media (prefers-reduced-motion: reduce) {{ .fadein {{ animation: none; opacity: 1; }} }}
  </style>
  <rect width="{w}" height="{h}" rx="10" fill="{BG}"/>
"""


def ring(cx, cy, r, fraction, color, width=9):
    import math

    circ = 2 * math.pi * r
    dash = max(0.02, min(fraction, 1.0)) * circ
    return f"""
  <circle cx="{cx}" cy="{cy}" r="{r}" stroke="#21262d" stroke-width="{width}"/>
  <circle cx="{cx}" cy="{cy}" r="{r}" stroke="{color}" stroke-width="{width}"
          stroke-linecap="round" stroke-dasharray="{dash:.1f} {circ:.1f}"
          transform="rotate(-90 {cx} {cy})"/>"""


def stats_card(s):
    w, h = 500, 200
    rows = [
        ("Commits", s["commits"], TEAL),
        ("Stars earned", s["stars"], YELLOW),
        ("Pull requests", s["prs"], PINK_BRIGHT),
        ("Issues", s["issues"], PERIWINKLE),
    ]
    max_v = max(v for _, v, _ in rows) or 1
    bar_x, bar_w = 240, 170
    parts = [svg_header(w, h, f"{s['name']}'s GitHub stats")]
    parts.append(f'<text x="25" y="35" class="title">{s["name"]}&#8217;s GitHub Stats</text>')
    # donut: contributions this year, fraction of active days
    parts.append(f'<g class="fadein">{ring(95, 122, 52, s["active_days"] / 366, PINK)}</g>')
    parts.append(f'<text x="95" y="122" text-anchor="middle" class="big" dominant-baseline="middle">{s["total_contrib"]}</text>')
    parts.append(f'<text x="95" y="150" text-anchor="middle" class="muted">contributions</text>')
    parts.append(f'<text x="95" y="164" text-anchor="middle" class="muted">last year</text>')
    y = 70
    for i, (label, v, color) in enumerate(rows):
        frac = v / max_v
        parts.append(f'<g class="fadein" style="animation-delay:{0.15 * i:.2f}s">')
        parts.append(f'<text x="{bar_x - 10}" y="{y + 4}" text-anchor="end" class="label">{label}</text>')
        parts.append(f'<rect x="{bar_x}" y="{y - 5}" width="{bar_w}" height="9" rx="4.5" fill="#21262d"/>')
        parts.append(f'<rect x="{bar_x}" y="{y - 5}" width="{max(6, frac * bar_w):.1f}" height="9" rx="4.5" fill="{color}"/>')
        parts.append(f'<text x="{bar_x + bar_w + 12}" y="{y + 4}" class="value">{v}</text>')
        parts.append("</g>")
        y += 34
    parts.append("</svg>")
    return "".join(parts)


def streak_card(s):
    w, h = 500, 180
    parts = [svg_header(w, h, "Contribution streaks")]
    # left: total
    parts.append(f'<g class="fadein"><text x="95" y="82" text-anchor="middle" class="mid">{s["total_contrib"]}</text>')
    parts.append(f'<text x="95" y="106" text-anchor="middle" class="label">Total contributions</text>')
    parts.append(f'<text x="95" y="124" text-anchor="middle" class="muted">last 12 months</text></g>')
    # middle: current streak in a ring
    parts.append(f'<g class="fadein" style="animation-delay:.15s">{ring(250, 88, 46, min(s["current_streak"] / 100, 1), PINK_BRIGHT)}')
    parts.append(f'<text x="250" y="84" text-anchor="middle" class="mid" dominant-baseline="middle">{s["current_streak"]}</text>')
    parts.append(f'<text x="250" y="112" text-anchor="middle" class="muted">days</text>')
    parts.append(f'<text x="250" y="158" text-anchor="middle" class="label" fill="{PINK_BRIGHT}" style="fill:{PINK_BRIGHT};font-weight:600">Current streak</text></g>')
    # right: longest
    parts.append(f'<g class="fadein" style="animation-delay:.3s"><text x="405" y="82" text-anchor="middle" class="mid">{s["longest_streak"]}</text>')
    parts.append(f'<text x="405" y="106" text-anchor="middle" class="label">Longest streak</text>')
    parts.append(f'<text x="405" y="124" text-anchor="middle" class="muted">{s["active_days"]} active days</text></g>')
    parts.append("</svg>")
    return "".join(parts)


def langs_card(s):
    w = 350
    h = 90 + ((len(s["langs"]) + 1) // 2) * 26
    parts = [svg_header(w, h, "Most used languages")]
    parts.append('<text x="25" y="35" class="title">Most Used Languages</text>')
    # stacked bar
    x = 25.0
    bar_w = w - 50
    parts.append(f'<g class="fadein">')
    for name, color, frac in s["langs"]:
        seg = frac * bar_w
        parts.append(f'<rect x="{x:.1f}" y="52" width="{max(seg, 2):.1f}" height="10" fill="{color}"/>')
        x += seg
    parts.append(f'<rect x="25" y="52" width="{bar_w}" height="10" rx="5" fill="none" stroke="{BG}" stroke-width="0"/>')
    parts.append("</g>")
    # legend, two columns
    for i, (name, color, frac) in enumerate(s["langs"]):
        col, row = i % 2, i // 2
        lx = 25 + col * (bar_w / 2 + 10)
        ly = 90 + row * 26
        parts.append(f'<g class="fadein" style="animation-delay:{0.1 * i:.2f}s">')
        parts.append(f'<circle cx="{lx}" cy="{ly - 4}" r="5" fill="{color}"/>')
        parts.append(f'<text x="{lx + 12}" y="{ly}" class="label">{name}</text>')
        parts.append(f'<text x="{lx + 12 + 95}" y="{ly}" class="muted">{frac * 100:.1f}%</text>')
        parts.append("</g>")
    parts.append("</svg>")
    return "".join(parts)


def main():
    user = sample_data() if os.environ.get("TEST_MODE") else fetch_data()
    s = compute(user)
    os.makedirs(OUT_DIR, exist_ok=True)
    for fname, svg in [
        ("stats.svg", stats_card(s)),
        ("streak.svg", streak_card(s)),
        ("top-langs.svg", langs_card(s)),
    ]:
        path = os.path.join(OUT_DIR, fname)
        with open(path, "w") as f:
            f.write(svg)
        print(f"wrote {path}")
    print(json.dumps({k: v for k, v in s.items() if k != "langs"}, indent=2))


if __name__ == "__main__":
    main()
