#!/usr/bin/env python3
"""
Generate every visual piece of the profile README as SVG:
  header.svg          Pinyon Script wordmark + Cormorant subtitle
  h-*.svg             section headings, Cormorant Garamond Light
  stats.svg           contributions, commits, stars, PRs, issues
  streak.svg          total / current / longest streak
  top-langs.svg       language breakdown

Data comes from the GitHub GraphQL API (the Actions token is enough).
Type is converted to vector paths, because GitHub's image proxy will not
load webfonts - naming a font-family would just fall back to the visitor's
default serif.

Env:
  GITHUB_TOKEN   provided automatically in GitHub Actions
  GH_LOGIN       GitHub username           (default: Sissighn)
  FONT_DIR       where the .ttf files live (default: fonts)
  OUT_DIR        where to write the SVGs   (default: assets)
  TEST_MODE=1    render with sample data, no API call
"""

import json
import math
import os
import urllib.request

from typo import Face, text_path

# ---------------------------------------------------------------- palette --
BG = "#0d1117"
ROSE = "#f2b8d4"     # wordmark, headings
PINK = "#d16ba5"     # primary accent
PINK_HI = "#ff6ec7"  # highlight / streak
TEXT = "#c9d1d9"
MUTED = "#8b949e"
TRACK = "#21262d"    # unfilled bar / ring
TEAL = "#2dd4bf"
GOLD = "#e3b341"
BLUE = "#86a8e7"

LOGIN = os.environ.get("GH_LOGIN", "Sissighn")
FONT_DIR = os.environ.get("FONT_DIR", "fonts")
OUT_DIR = os.environ.get("OUT_DIR", "assets")

script = Face(os.path.join(FONT_DIR, "PinyonScript-Regular.ttf"))
corm = Face(os.path.join(FONT_DIR, "CormorantGaramond-var.ttf"), wght=300)
corm_m = Face(os.path.join(FONT_DIR, "CormorantGaramond-var.ttf"), wght=500)


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
    body = json.dumps({"query": QUERY, "variables": {"login": LOGIN}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"bearer {os.environ['GITHUB_TOKEN']}",
            "Content-Type": "application/json",
            "User-Agent": "profile-cards",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    if "errors" in payload:
        raise RuntimeError(payload["errors"])
    return payload["data"]["user"]


def sample_data():
    import datetime as dt
    import random

    random.seed(7)
    today = dt.date.today()
    days = [
        {
            "date": (today - dt.timedelta(days=i)).isoformat(),
            "contributionCount": random.choice([0, 1, 2, 3, 5, 8]) if random.random() > 0.2 else 0,
        }
        for i in range(365, -1, -1)
    ]
    for d in days[-19:]:
        d["contributionCount"] = max(1, d["contributionCount"])
    weeks = [{"contributionDays": days[i : i + 7]} for i in range(0, len(days), 7)]
    return {
        "name": "Sissi",
        "followers": {"totalCount": 2},
        "pullRequests": {"totalCount": 87},
        "issues": {"totalCount": 34},
        "contributionsCollection": {
            "totalCommitContributions": 812,
            "contributionCalendar": {"totalContributions": 1043, "weeks": weeks},
        },
        "repositories": {
            "totalCount": 12,
            "nodes": [
                {"stargazerCount": 2, "languages": {"edges": [
                    {"size": 52000, "node": {"name": "Python", "color": "#3572A5"}},
                    {"size": 31000, "node": {"name": "Java", "color": "#b07219"}}]}},
                {"stargazerCount": 1, "languages": {"edges": [
                    {"size": 48000, "node": {"name": "TypeScript", "color": "#3178c6"}},
                    {"size": 22000, "node": {"name": "JavaScript", "color": "#f1e05a"}},
                    {"size": 9000, "node": {"name": "CSS", "color": "#563d7c"}}]}},
                {"stargazerCount": 0, "languages": {"edges": [
                    {"size": 30000, "node": {"name": "C++", "color": "#f34b7d"}},
                    {"size": 5000, "node": {"name": "HTML", "color": "#e34c26"}}]}},
            ],
        },
    }


def compute(user):
    cal = user["contributionsCollection"]["contributionCalendar"]
    days = sorted(
        (d for w in cal["weeks"] for d in w["contributionDays"]),
        key=lambda d: d["date"],
    )

    longest = run = 0
    for d in days:
        run = run + 1 if d["contributionCount"] > 0 else 0
        longest = max(longest, run)

    current = 0
    for i, d in enumerate(reversed(days)):
        if d["contributionCount"] > 0:
            current += 1
        elif i == 0:
            continue  # today with no commits yet doesn't end the streak
        else:
            break

    langs = {}
    for repo in user["repositories"]["nodes"]:
        for e in repo["languages"]["edges"]:
            n = e["node"]["name"]
            langs.setdefault(n, {"size": 0, "color": e["node"]["color"] or MUTED})
            langs[n]["size"] += e["size"]
    top = sorted(langs.items(), key=lambda kv: kv[1]["size"], reverse=True)[:6]
    tot = sum(v["size"] for _, v in top) or 1

    return {
        "name": user["name"] or LOGIN,
        "total": cal["totalContributions"],
        "commits": user["contributionsCollection"]["totalCommitContributions"],
        "prs": user["pullRequests"]["totalCount"],
        "issues": user["issues"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in user["repositories"]["nodes"]),
        "repos": user["repositories"]["totalCount"],
        "current": current,
        "longest": longest,
        "active": sum(1 for d in days if d["contributionCount"] > 0),
        "langs": [(n, v["color"], v["size"] / tot) for n, v in top],
    }


# -------------------------------------------------------------- svg parts --
def head(w, h, label):
    return (
        f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="{label}">'
    )


def card_bg(w, h):
    return f'<rect width="{w}" height="{h}" rx="10" fill="{BG}"/>'


def ring(cx, cy, r, frac, color, width=8):
    circ = 2 * math.pi * r
    dash = max(0.015, min(frac, 1.0)) * circ
    return (
        f'<circle cx="{cx}" cy="{cy}" r="{r}" stroke="{TRACK}" stroke-width="{width}" fill="none"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{r}" stroke="{color}" stroke-width="{width}" fill="none" '
        f'stroke-linecap="round" stroke-dasharray="{dash:.1f} {circ:.1f}" '
        f'transform="rotate(-90 {cx} {cy})"/>'
    )


def header_svg():
    # transparent - no card, just the wordmark and its hairline
    w, h = 900, 160
    p = [head(w, h, "Sissi")]
    p.append(text_path(script, "Sissi", 96, w / 2, 108, ROSE, anchor="middle"))
    p.append(
        f'<line x1="{w/2-90}" y1="138" x2="{w/2+90}" y2="138" '
        f'stroke="{PINK}" stroke-width="0.75" opacity="0.5"/>'
    )
    p.append("</svg>")
    return "".join(p)


def heading_svg(label):
    # transparent, no trailing rule - just the words
    size = 22
    tw = corm.width(label, size, tracking=1.2)
    w, h = int(tw) + 10, 34
    p = [head(w, h, label)]
    p.append(text_path(corm, label, size, 2, 25, ROSE, tracking=1.2))
    p.append("</svg>")
    return "".join(p)


def streak_svg(s):
    w, h = 500, 190
    p = [head(w, h, "Contribution streak"), card_bg(w, h)]

    p.append(text_path(corm_m, str(s["total"]), 34, 92, 84, "#ffffff", anchor="middle"))
    p.append(text_path(corm, "Total contributions", 18, 92, 112, TEXT, tracking=0.5, anchor="middle"))
    p.append(text_path(corm, "last 12 months", 15, 92, 132, MUTED, tracking=0.5, anchor="middle"))

    p.append(ring(250, 88, 48, min(s["current"] / 100, 1.0), PINK_HI, 8))
    p.append(text_path(corm_m, str(s["current"]), 38, 250, 96, "#ffffff", anchor="middle"))
    p.append(text_path(corm, "Current streak", 19, 250, 168, PINK_HI, tracking=0.6, anchor="middle"))

    p.append(text_path(corm_m, str(s["longest"]), 34, 408, 84, "#ffffff", anchor="middle"))
    p.append(text_path(corm, "Longest streak", 18, 408, 112, TEXT, tracking=0.5, anchor="middle"))
    p.append(
        text_path(corm, f"{s['active']} active days", 15, 408, 132, MUTED, tracking=0.5, anchor="middle")
    )

    p.append(f'<line x1="171" y1="46" x2="171" y2="146" stroke="{TRACK}"/>')
    p.append(f'<line x1="329" y1="46" x2="329" y2="146" stroke="{TRACK}"/>')
    p.append("</svg>")
    return "".join(p)


def langs_svg(s):
    # one language per row: name left, percentage right - long names
    # like "Jupyter Notebook" can never collide with the numbers
    w = 360
    h = 92 + len(s["langs"]) * 27
    p = [head(w, h, "Most used languages"), card_bg(w, h)]
    p.append(text_path(corm, "Most Used Languages", 24, 24, 42, ROSE, tracking=1.0))

    bw = w - 48
    x = 24.0
    p.append(f'<clipPath id="r"><rect x="24" y="58" width="{bw}" height="9" rx="4.5"/></clipPath>')
    p.append('<g clip-path="url(#r)">')
    for _, color, frac in s["langs"]:
        seg = frac * bw
        p.append(f'<rect x="{x:.1f}" y="58" width="{max(seg, 2):.1f}" height="9" fill="{color}"/>')
        x += seg
    p.append("</g>")

    for i, (name, color, frac) in enumerate(s["langs"]):
        ly = 100 + i * 27
        p.append(f'<circle cx="29" cy="{ly - 5}" r="5" fill="{color}"/>')
        p.append(text_path(corm, name, 18, 42, ly, TEXT, tracking=0.4))
        p.append(text_path(corm, f"{frac * 100:.1f}%", 16, w - 24, ly, MUTED, anchor="end"))
    p.append("</svg>")
    return "".join(p)


HEADINGS = {
    "about": "About Me",
    "stack": "Tech Stack",
    "stats": "GitHub Stats",
    "badges": "Badges",
    "activity": "Activity",
    "projects": "Featured Projects",
}


def main():
    user = sample_data() if os.environ.get("TEST_MODE") else fetch_data()
    s = compute(user)
    os.makedirs(OUT_DIR, exist_ok=True)

    files = {
        "header.svg": header_svg(),
        "streak.svg": streak_svg(s),
        "top-langs.svg": langs_svg(s),
    }
    for key, label in HEADINGS.items():
        files[f"h-{key}.svg"] = heading_svg(label)

    for name, svg in files.items():
        with open(os.path.join(OUT_DIR, name), "w") as f:
            f.write(svg)
        print(f"wrote {OUT_DIR}/{name}")
    print(json.dumps({k: v for k, v in s.items() if k != "langs"}, indent=2))


if __name__ == "__main__":
    main()
