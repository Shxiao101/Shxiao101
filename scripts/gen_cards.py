#!/usr/bin/env python3
"""Render the profile's stats panel, bookshelf, preface & contents book page and works-in-progress ledge as themed
SVGs, and frame the contribution snake.

Runs in GitHub Actions (see .github/workflows/cards.yml) and writes dist/{stats,shelf,toc,works}-{dark,light}.svg.
If Platane/snk has already left dist/snake-{dark,light}.svg there, they are framed as the contributions card
(a local run without them just skips it).
Only the standard library is used. Fonts are embedded from scripts/fonts.json (which also carries their advance
widths, for measuring text), the panel illustration from scripts/stats.jpg (see prep_images.py).
Repositories, stars, languages, commits, pull requests and issues count public work only, so a local run with a
personal token matches the Actions run.  The calendar and streaks are github's own contribution calendar, which
includes private contributions only as far as the token's viewer may see them (or the profile shares them).
"""
import base64
import datetime as dt
import html
import json
import os
import random
import re
import sys
import unicodedata
import urllib.request

from common import EASE, FONTS, fontface, smooth_fade, star_path, write_svg
from maple import LEAF_COLORS, STALK_END, leaf_def
from paper import punch
from sunlight import light_rays

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "dist")
LOGIN = os.environ.get("GH_LOGIN", "Shxiao101")
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")

# ---- the preface: the left page of the book card, beside the contents -----------------------------
PREFACE = [                      # (icon, text): icons are "cap", "books" or "blossom"; \n breaks the line
    ("cap", "A sophomore in\nComputer Science and Technology"),
    ("books", "A member of BYR Docs"),
    ("blossom", "She is Amano Tooko.\nAs you can see, a literary girl."),
]
PREFACE_NAMES = ["BYR Docs", "Amano Tooko"]   # inked in the accent colour
# --------------------------------------------------------------------------------------------------

STATS_IMG = base64.b64encode(open(os.path.join(HERE, "stats.jpg"), "rb").read()).decode()

# pull requests and issues through search, which can be limited to public repositories; user.pullRequests can't
QUERY = """
query($login: String!, $prs: String!, $issues: String!) {
  prs: search(query: $prs, type: ISSUE, first: 1) { issueCount }
  issues: search(query: $issues, type: ISSUE, first: 1) { issueCount }
  user(login: $login) {
    contributionsCollection {
      commitContributionsByRepository(maxRepositories: 100) { repository { isPrivate } contributions { totalCount } }
      contributionCalendar { weeks { contributionDays { date contributionCount } } }
    }
    pinnedItems(first: 6, types: REPOSITORY) {
      nodes {
        ... on Repository {
          name description isPrivate pushedAt stargazerCount forkCount owner { login }
          languages(first: 10, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name color } } }
        }
      }
    }
  }
}
"""
REPOS_QUERY = """
query($login: String!, $after: String) {
  user(login: $login) {
    repositories(first: 100, after: $after, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, orderBy: {field: STARGAZERS, direction: DESC}) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        name description pushedAt stargazerCount forkCount owner { login }
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""


def gql(query, variables):
    if not TOKEN:
        sys.exit("GITHUB_TOKEN is not set")
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql", data=body,
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json",
                 "User-Agent": "profile-cards"})
    res = json.load(urllib.request.urlopen(req, timeout=60))
    if res.get("errors"):
        sys.exit(json.dumps(res["errors"], indent=2))
    return res["data"]


YEARS_QUERY = "query($login: String!) { user(login: $login) { contributionsCollection { contributionYears } } }"


def all_days():
    """Every calendar day of every contribution year, as sorted (date, count) pairs."""
    years = gql(YEARS_QUERY, {"login": LOGIN})["user"]["contributionsCollection"]["contributionYears"]
    if not years:
        return []
    fields = " ".join(
        f'y{y}: contributionsCollection(from: "{y}-01-01T00:00:00Z", to: "{y}-12-31T23:59:59Z") '
        "{ contributionCalendar { weeks { contributionDays { date contributionCount } } } }" for y in years)
    u = gql("query($login: String!) { user(login: $login) { %s } }" % fields, {"login": LOGIN})["user"]
    days = {}
    for y in years:
        for w in u[f"y{y}"]["contributionCalendar"]["weeks"]:
            for day in w["contributionDays"]:
                days[day["date"]] = day["contributionCount"]
    return sorted(days.items())


def all_repos():
    """(total count, every public non-fork repository I own), a page of 100 at a time."""
    repos, after = [], None
    while True:
        page = gql(REPOS_QUERY, {"login": LOGIN, "after": after})["user"]["repositories"]
        repos += page["nodes"]
        if not page["pageInfo"]["hasNextPage"]:
            return page["totalCount"], repos
        after = page["pageInfo"]["endCursor"]


def streaks(days, today):
    """All-time total plus current and longest streak as (length, first day, last day).
    Input is sorted by date. Missing dates break a streak.
    Today still counts as open: a streak that ran through yesterday is kept."""
    days = [(dt.date.fromisoformat(k), c) for k, c in days if dt.date.fromisoformat(k) <= today]
    longest, run, start = (0, None, None), 0, None
    previous = None
    for day, c in days:
        if previous is not None and day != previous + dt.timedelta(days=1):
            run = 0
        if c > 0:
            start = day if run == 0 else start
            run += 1
            if run > longest[0]:
                longest = (run, start, day)
        else:
            run = 0
        previous = day
    i = len(days) - 1
    if i >= 0 and days[i] == (today, 0):
        i -= 1
    end, n = (days[i][0] if i >= 0 else None), 0
    expected = end if end in (today, today - dt.timedelta(days=1)) else None
    while i >= 0 and days[i][0] == expected and days[i][1] > 0:
        n += 1
        expected -= dt.timedelta(days=1)
        i -= 1
    current = (n, days[i + 1][0], end) if n else (0, None, None)
    first = next((day for day, c in days if c > 0), None)
    return {"total": sum(c for _, c in days), "current": current, "longest": longest, "first": first}


SKIP_LANGS = {"XSLT", "Makefile", "DTrace", "HTML", "Shell", "Batchfile", "CMake"}


def collect():
    res = gql(QUERY, {"login": LOGIN, "prs": f"author:{LOGIN} is:pr is:public",
                      "issues": f"author:{LOGIN} is:issue is:public"})
    u = res["user"]
    repo_count, repos = all_repos()
    langs, colors = {}, {}
    for r in repos:
        for e in r["languages"]["edges"]:
            name = e["node"]["name"]
            if name in SKIP_LANGS:
                continue
            langs[name] = langs.get(name, 0) + e["size"]
            colors[name] = e["node"]["color"]
    total_lang = sum(langs.values()) or 1
    # the six biggest, leaving out slivers under half a percent
    top = [(n, s / total_lang, colors[n]) for n, s in sorted(langs.items(), key=lambda kv: -kv[1])
           if s / total_lang >= .005][:6]
    # my own repositories, latest first; the profile repository itself is where the reader already is
    own = sorted((r for r in repos if r["name"].lower() != LOGIN.lower()), key=lambda r: r["pushedAt"], reverse=True)
    # chapter ii: the pinned repositories, or while nothing is pinned, my most starred (repos come starred-first)
    pinned = [r for r in u["pinnedItems"]["nodes"] if r and not r["isPrivate"]]
    works = [volume(r) for r in (pinned or [r for r in repos if r["name"].lower() != LOGIN.lower()])[:WORKS_MAX]]
    cc = u["contributionsCollection"]
    days = [(d["date"], d["contributionCount"]) for w in cc["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    today = dt.date.fromisoformat(days[-1][0])   # the calendar ends on github's "today"
    return {
        "today": today,
        "streak": streaks(all_days(), today),
        "stars": sum(r["stargazerCount"] for r in repos),
        "repos": repo_count,
        # public commits over the calendar's 12 months; restrictedContributionsCount would add private PRs and
        # reviews too, not just commits
        "commits": sum(r["contributions"]["totalCount"] for r in cc["commitContributionsByRepository"]
                       if not r["repository"]["isPrivate"]),
        "prs": res["prs"]["issueCount"],
        "issues": res["issues"]["issueCount"],
        "active_days": sum(1 for _, c in days if c > 0),
        "days_count": len(days),
        "langs": top,
        "own": [{"name": r["name"], "pushed": dt.date.fromisoformat(r["pushedAt"][:10]),
                 "desc": " ".join((r["description"] or "").split()),
                 "langs": [e["node"]["name"] for e in r["languages"]["edges"] if e["node"]["name"] not in SKIP_LANGS]}
                for r in own],
        "works": works,
        "works_pinned": bool(pinned),
    }


def volume(r):
    """A repository as one volume of the works-in-progress card: its main language dyes the cover cloth."""
    lang = next((e["node"] for e in r["languages"]["edges"] if e["node"]["name"] not in SKIP_LANGS), None)
    return {"name": r["name"], "owner": r["owner"]["login"], "desc": " ".join((r["description"] or "").split()),
            "stars": r["stargazerCount"], "forks": r["forkCount"],
            "pushed": dt.date.fromisoformat(r["pushedAt"][:10]),
            "lang": lang["name"] if lang else "", "color": lang["color"] if lang else None}


PAL = {
    "dark": dict(
        bg0="#1b180e", bg1="#121210", border="#3a3418",
        title="#fbf6e0", label="#c2b788", value="#fbf6e0", muted="#9a9068",
        accent="#e4cf5a", accent2="#a0a741", track="#2c2814",
        langs=["#f2e173", "#d9b84a", "#a0a741", "#6fb8a8", "#f5d49f", "#b38f2e"],
        grad0="#ffffff", grad1="#e4cf5a",
        pbg0="#1b180e", pbg1="#121210", pbg2="#0d1413", frame="#e8d98a", frameO=".20", grainO=".045",
        blobA="#c9a227", blobAo=".26", blobB="#2f6b62", blobBo=".34", blobC="#8b6fb0", blobCo=".22",
        spark="#fff2b0", toneR="0 .5 .9", toneG="0 .46 .82", toneB="0 .4 .7",
        # bookshelf and contents page
        wood="#6b4a2a", wood0="#553820", wood1="#3a2613", woodLine="#1e1208", wallShade="#000", wallShadeO=".55",
        bookShade="#000", bookShadeO=".55", clothDim=".2", foil="#ecd27a", foilDark="#2a1d0a",
        vase0="#7aa593", vase1="#3c5c50", metal0="#8a826c", metal1="#4a453a", stem="#8a5a32",
        ribbon0="#e0552a", ribbon1="#9c3a18", ribbonShadeO=".35", gutter="#000", gutterO=".42",
        nextPage="#221e13", flap0="#0e0d08", flap1="#5c5238", flap2="#39321f", flap3="#282316", curlShadeO=".5", blossom="#f2a2b5",
        # works-in-progress covers: the obi (paper band round the foot of a cover) and its print, the jacket
        obi="#e9dcb8", obiInk="#b33d19", obiText="#3a2c14", obiMuted="#7a6a48", glintO=".16",
        paper="#efe6cf", ink="#2b2418", inkMuted="#6d604a", coverDim=".12"),
    "light": dict(
        bg0="#fffdf3", bg1="#f8f2d8", border="#e6dcae",
        title="#3b340c", label="#6f6434", value="#3b340c", muted="#8f8454",
        accent="#a8841a", accent2="#6f7a1a", track="#eee5bf",
        langs=["#a8841a", "#d4b64a", "#6f7a1a", "#3f8f7f", "#d49a5a", "#5e4c0c"],
        grad0="#3b340c", grad1="#a8841a",
        pbg0="#faf4d9", pbg1="#fffdf3", pbg2="#f0f2df", frame="#8a7a1a", frameO=".18", grainO=".03",
        blobA="#f2e173", blobAo=".50", blobB="#d8e3a4", blobBo=".55", blobC="#e6dcf5", blobCo=".70",
        spark="#b8921c", toneR="0 1", toneG="0 1", toneB="0 1",
        wood="#dcb682", wood0="#c0915a", wood1="#9a6a38", woodLine="#6b4520", wallShade="#7a5a2a", wallShadeO=".22",
        bookShade="#5a4520", bookShadeO=".22", clothDim="0", foil="#f3d98a", foilDark="#3a2a10",
        vase0="#b3d0c1", vase1="#6f9483", metal0="#c2b9a2", metal1="#7d7462", stem="#7a5230",
        ribbon0="#d9481c", ribbon1="#a82a10", ribbonShadeO=".16", gutter="#6b5a2a", gutterO=".16",
        nextPage="#efe4c3", flap0="#cdbb86", flap1="#fffbef", flap2="#f3e8cb", flap3="#e4d5aa", curlShadeO=".16", blossom="#dc7690",
        obi="#fbf4e0", obiInk="#c23f16", obiText="#3b340c", obiMuted="#8f8454", glintO=".22",
        paper="#fffbf2", ink="#2b2418", inkMuted="#6d604a", coverDim="0"),
}


CSS = (fontface("outfit") + fontface("jbmono") +
       ".t{font-family:'Outfit',sans-serif;font-weight:800}"
       ".m{font-family:'JetBrains Mono',monospace;font-weight:500}"
       "@keyframes bar{from{transform:scaleX(0)}to{transform:scaleX(1)}}"
       ".b{transform-origin:left;animation:bar 1.2s cubic-bezier(.2,.8,.2,1) .2s both}")

ICON = {
    "star": '<path d="M0,-6.5 L1.9,-2 L6.5,-1.7 L2.9,1.4 L4,6 L0,3.5 L-4,6 L-2.9,1.4 L-6.5,-1.7 L-1.9,-2 Z"/>',
    "commit": '<circle r="3.2" fill="none" stroke-width="1.8"/><path d="M-7.5,0 H-3.2 M3.2,0 H7.5" stroke-width="1.8"/>',
    "pr": ('<circle cx="-4" cy="-4.2" r="2.1" fill="none" stroke-width="1.6"/>'
           '<circle cx="-4" cy="4.6" r="2.1" fill="none" stroke-width="1.6"/>'
           '<circle cx="4.6" cy="4.6" r="2.1" fill="none" stroke-width="1.6"/>'
           '<path d="M-4,-2.1 V2.5 M4.6,2.5 V-0.8 Q4.6,-4.2 1.2,-4.2 H-0.6" fill="none" stroke-width="1.6"/>'),
    "issue": '<circle r="6" fill="none" stroke-width="1.8"/><circle r="1.7"/>',
    "repo": '<path d="M-5,-6.5 H5 V6.5 H-3.4 Q-5,6.5 -5,4.9 Z M-5,3.3 H5" fill="none" stroke-width="1.6"/>',
}


def fmt(n):
    return f"{n/1000:.1f}k" if n >= 10000 else f"{n:,}"


def esc(s):
    return html.escape(s, quote=True)


def text_width(key, text, size, spacing=0.0):
    """Advance width in px from the tables in fonts.json (printable ASCII); anything else falls back to a system
    font, so guess: 1em for wide CJK characters, .6em otherwise."""
    adv = FONTS[key]["adv"]
    w = 0.0
    for ch in text:
        o = ord(ch)
        if 32 <= o < 127:
            w += adv[o - 32] / 1000 * size
        else:
            w += size if unicodedata.east_asian_width(ch) in "WF" else size * .6
        w += spacing
    return w


def clip_text(key, text, size, max_w):
    """`text`, cut short with an ellipsis if it is wider than max_w."""
    if text_width(key, text, size) <= max_w:
        return text
    while text and text_width(key, text + "...", size) > max_w:
        text = text[:-1]
    return text.rstrip(" ,.;:-，。、") + "..."


def rgb(c):
    c = c.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return [int(c[i:i + 2], 16) for i in (0, 2, 4)]


def mix(a, b, t):
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(rgb(a), rgb(b)))


def luma(c):
    r, g, b = (v / 255 for v in rgb(c))
    return .2126 * r + .7152 * g + .0722 * b


def card_frame(p, w, h, gid):
    return (f'<defs><style><![CDATA[{CSS}]]></style>'
            f'<linearGradient id="bg{gid}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{p["bg0"]}"/><stop offset="1" stop-color="{p["bg1"]}"/></linearGradient>'
            f'<linearGradient id="tg{gid}" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{p["grad0"]}"/><stop offset="1" stop-color="{p["grad1"]}"/></linearGradient>'
            f'<linearGradient id="rg{gid}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{p["accent"]}"/><stop offset="1" stop-color="{p["accent2"]}"/></linearGradient>'
            f'</defs>'
            f'<rect x="0.75" y="0.75" width="{w-1.5}" height="{h-1.5}" rx="16" fill="url(#bg{gid})" stroke="{p["border"]}" stroke-width="1.5"/>')


def date_span(a, b):
    f = lambda d: f"{d.strftime('%b').lower()} {d.day}"
    return f(a) if a == b else f"{f(a)} - {f(b)}"


def stats_panel(theme, d):
    """Stats on the left, the window illustration (scripts/stats.jpg) fading in on the right."""
    p = PAL[theme]
    W, H = 1200, 480
    IW = 524                      # stats.jpg is 1048x960 -> 524x480
    ix = W - IW
    s = d["streak"]
    cur_n, cur_a, cur_b = s["current"]
    long_n, long_a, long_b = s["longest"]
    since = f"since {s['first'].strftime('%b').lower()} {s['first'].year}" if s["first"] else "no contributions yet"
    big = [
        (fmt(s["total"]), "total contributions", since, False),
        (fmt(cur_n), "current streak", date_span(cur_a, cur_b) if cur_n else "start one today", True),
        (fmt(long_n), "longest streak", date_span(long_a, long_b) if long_n else "-", False),
    ]
    body = []
    for i, (val, label, sub, hot) in enumerate(big):
        x = 56 + i * 200
        fill = "url(#pgrad)" if hot else p["value"]
        if hot:
            body.append(f'<text x="{x}" y="172" class="t" font-size="56" letter-spacing="-1" fill="{p["accent"]}" opacity=".5" filter="url(#pglow)">{val}</text>')
        body.append(f'<text x="{x}" y="172" class="t" font-size="56" letter-spacing="-1" fill="{fill}">{val}</text>')
        body.append(f'<text x="{x}" y="202" class="m" font-size="12.5" fill="{p["label"]}">{label}</text>')
        body.append(f'<text x="{x}" y="222" class="m" font-size="11" fill="{p["muted"]}">{sub}</text>')
    # pline is laid out in user space: a gradient sized to a horizontal line's zero-height box isn't painted
    body.append('<line x1="56" y1="262" x2="636" y2="262" stroke="url(#pline)" stroke-width="1.2"/>')
    rows = [("star", "stars", d["stars"]), ("commit", "commits · 1y", d["commits"]),
            ("pr", "pull requests", d["prs"]), ("issue", "issues", d["issues"]), ("repo", "repos", d["repos"])]
    for i, (ic, label, val) in enumerate(rows):
        x = 56 + i * 118
        body.append(f'<g transform="translate({x+7} 300)" fill="{p["accent"]}" stroke="{p["accent"]}" stroke-linecap="round" stroke-linejoin="round">{ICON[ic]}</g>')
        body.append(f'<text x="{x}" y="346" class="t" font-size="28" fill="{p["value"]}">{fmt(val)}</text>')
        body.append(f'<text x="{x}" y="368" class="m" font-size="11.5" fill="{p["label"]}">{label}</text>')
    frac = d["active_days"] / max(d["days_count"], 1)
    body.append(f'<text x="56" y="408" class="m" font-size="12" fill="{p["label"]}">{d["active_days"]} active days</text>'
                f'<text x="636" y="408" class="m" font-size="11" text-anchor="end" fill="{p["muted"]}">last 12 months</text>'
                f'<rect x="56" y="420" width="580" height="8" rx="4" fill="{p["track"]}"/>'
                f'<rect class="b" style="transform-box:fill-box" x="56" y="420" width="{580*frac:.1f}" height="8" rx="4" fill="url(#pbar)"/>')
    sparks = "".join(
        f'<g transform="translate({x} {y})"><path d="{star_path(r)}" fill="{p["spark"]}">'
        f'<animate attributeName="opacity" values="0.15;1;0.15" dur="{dur}s" begin="{beg}s" repeatCount="indefinite"/></path></g>'
        for x, y, r, dur, beg in [(640, 58, 7, 3.2, 0), (604, 236, 5, 2.7, 1.1), (1150, 430, 8, 3.6, .5), (700, 448, 5, 2.9, 1.8)])
    # light and shade over the numbers, falling from the upper right to the lower left (mirror of the hero)
    sun_defs, sun = light_rays("sunS", 30, 700, H, theme == "dark", from_left=False, seed=9)
    today = d["today"]
    updated = f"updated {today.strftime('%b').lower()} {today.day}, {today.year}"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="github stats of {LOGIN}">
<defs><style><![CDATA[{CSS}]]></style>
<clipPath id="pcard"><rect width="{W}" height="{H}" rx="28" ry="28"/></clipPath>
<linearGradient id="pbg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{p['pbg0']}"/><stop offset=".55" stop-color="{p['pbg1']}"/><stop offset="1" stop-color="{p['pbg2']}"/></linearGradient>
<linearGradient id="pgrad" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{p['grad0']}"/><stop offset="1" stop-color="{p['grad1']}"/></linearGradient>
<linearGradient id="pbar" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{p['accent2']}"/><stop offset="1" stop-color="{p['accent']}"/></linearGradient>
<linearGradient id="pline" gradientUnits="userSpaceOnUse" x1="56" y1="0" x2="636" y2="0"><stop offset="0" stop-color="{p['accent']}" stop-opacity=".7"/><stop offset="1" stop-color="{p['accent']}" stop-opacity="0"/></linearGradient>
<linearGradient id="pfade" gradientUnits="userSpaceOnUse" x1="{ix}" y1="0" x2="{ix+230}" y2="0">{smooth_fade(fade_in=True)}</linearGradient>
<mask id="pmask"><rect x="{ix}" y="0" width="{IW}" height="{H}" fill="url(#pfade)"/></mask>
<filter id="pblur" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="70"/></filter>
<filter id="pglow" x="-30%" y="-60%" width="160%" height="220%"><feGaussianBlur stdDeviation="14"/></filter>
<filter id="ptint" color-interpolation-filters="sRGB"><feComponentTransfer><feFuncR type="table" tableValues="{p['toneR']}"/><feFuncG type="table" tableValues="{p['toneG']}"/><feFuncB type="table" tableValues="{p['toneB']}"/></feComponentTransfer></filter>
<filter id="pgrain" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" stitchTiles="stitch"/><feColorMatrix type="saturate" values="0"/></filter>
{sun_defs}
</defs>
<g clip-path="url(#pcard)">
<rect width="{W}" height="{H}" fill="url(#pbg)"/>
<g filter="url(#pblur)">
<ellipse cx="300" cy="60" rx="380" ry="170" fill="{p['blobA']}" opacity="{p['blobAo']}"><animate attributeName="cx" values="300;400;300" dur="18s" repeatCount="indefinite"/></ellipse>
<ellipse cx="160" cy="470" rx="320" ry="140" fill="{p['blobB']}" opacity="{p['blobBo']}"/>
<ellipse cx="820" cy="300" rx="240" ry="220" fill="{p['blobC']}" opacity="{p['blobCo']}"><animate attributeName="rx" values="240;290;240" dur="15s" repeatCount="indefinite"/></ellipse>
</g>
<image href="data:image/jpeg;base64,{STATS_IMG}" x="{ix}" y="0" width="{IW}" height="{H}" preserveAspectRatio="xMidYMid slice" mask="url(#pmask)" filter="url(#ptint)"/>
{sun}
{sparks}
<rect width="{W}" height="{H}" filter="url(#pgrain)" opacity="{p['grainO']}"/>
<text x="56" y="84" class="m" font-size="13" letter-spacing="2.5" fill="{p['accent']}">github stats</text>
<text x="636" y="84" class="m" font-size="11" text-anchor="end" fill="{p['muted']}">{updated}</text>
{"".join(body)}
<rect x="1" y="1" width="{W-2}" height="{H-2}" rx="27" fill="none" stroke="{p['frame']}" stroke-opacity="{p['frameO']}" stroke-width="1.5"/>
</g>
</svg>'''


SHELF_Y = 258          # top of the shelf board, where the books stand


def spine_trim(style, x, y, w, foil, ornament):
    """Gilt work on a spine, the foot a mirror image of the head; every volume of one language shares a style,
    like a set.  The front of the shelf board hides the bottom 4px of each book, so the foot is measured from
    what shows."""
    head, foot = y, SHELF_Y - 4

    def mirrored(d, hh, piece):   # `piece(top_y)` d px in from the head, and again d px in from the foot
        return piece(head + d) + piece(foot - d - hh)

    def rule(d, hh=1.4, o=.85):
        return mirrored(d, hh, lambda yy: f'<rect x="{x + 2.5:.1f}" y="{yy:.1f}" width="{w - 5:.1f}" height="{hh}" fill="{foil}" opacity="{o}"/>')

    # a small gilt lozenge mid-spine where there's no title
    lozenge = (f'<rect x="-2.6" y="-2.6" width="5.2" height="5.2" transform="translate({x + w / 2:.1f} {(head + foot) / 2:.1f}) rotate(45)" '
               f'fill="{foil}" opacity=".7"/>' if ornament else "")
    if style == 0:        # double gilt rules
        return rule(11) + rule(15.5) + lozenge
    if style == 1:        # dark leather bands edged in gilt
        band = mirrored(9, 13, lambda yy: f'<rect x="{x:.1f}" y="{yy:.1f}" width="{w:.1f}" height="13" fill="#000" opacity=".24"/>')
        return band + rule(7.4, 1.2, .8) + rule(22.4, 1.2, .8) + lozenge
    return rule(12, 2.4) + lozenge   # one broad gilt rule


def vase(p, cx, base):
    """A celadon bud vase with a sprig of maple that sways a little, and now and then drops a leaf on the shelf."""
    rnd = random.Random(3)
    mouth = base - 54
    stems = ["M0,4 C-3,-22 -14,-44 -30,-66", "M1,4 C4,-26 10,-52 20,-86", "M0,4 C2,-14 0,-28 8,-44"]
    # (x, y, scale, angle): where a leaf's stalk joins a stem (at the tips and part way along), relative to the
    # mouth, and which way the leaf points
    spots = [(-30, -66, 1.0, -36), (-11.7, -35.9, .8, -72), (20, -86, 1.05, 16), (10.9, -52.7, .8, 62), (8, -44, .9, 24)]
    sx, sy = STALK_END
    leaves = []
    for x, y, s, a in spots:
        c = rnd.choice(LEAF_COLORS)
        dur, beg = rnd.uniform(3.5, 5.5), -rnd.uniform(0, 5)
        leaves.append(   # hung by the end of its stalk, so it sways about the stem
            f'<g transform="translate({x} {y}) rotate({a})"><g>'
            f'<animateTransform attributeName="transform" type="rotate" values="-7;7;-7" keyTimes="0;.5;1" calcMode="spline" '
            f'keySplines="{EASE};{EASE}" dur="{dur:.1f}s" begin="{beg:.1f}s" repeatCount="indefinite"/>'
            f'<use href="#vleaf" transform="scale({s}) translate({-sx} {-sy})" fill="{c}"/></g></g>')
    stems = "".join(f'<path d="{s}"/>' for s in stems)
    sprig = (f'<g transform="translate({cx} {mouth})"><g>'
             f'<animateTransform attributeName="transform" type="rotate" values="-1.6;1.6;-1.6" keyTimes="0;.5;1" calcMode="spline" '
             f'keySplines="{EASE};{EASE}" dur="7s" repeatCount="indefinite"/>'
             f'<g fill="none" stroke="{p["stem"]}" stroke-width="1.6" stroke-linecap="round">{stems}</g>'
             f'{"".join(leaves)}</g></g>')
    body = (f'<g transform="translate({cx} {base})">'
            f'<ellipse cx="5" cy="0" rx="22" ry="3" fill="#000" opacity=".2"/>'
            f'<path d="M-13,0 C-24,-6 -25,-30 -12,-40 C-8,-44 -7,-48 -8,-54 L8,-54 C7,-48 8,-44 12,-40 C25,-30 24,-6 13,0 Z" fill="url(#vaseG)"/>'
            f'<ellipse cx="0" cy="-54" rx="8.5" ry="2.2" fill="{p["vase1"]}"/>'
            f'<path d="M-15,-31 C-17,-21 -15,-11 -10,-5" fill="none" stroke="#fff" stroke-opacity=".38" stroke-width="2.4" stroke-linecap="round"/></g>')
    # the falling leaf: lets go of the sprig, flutters down, lies on the board a moment and fades
    kt = "0;.1;.2;.3;.4;1"
    spl = f'keyTimes="{kt}" calcMode="spline" keySplines="{";".join([EASE] * 5)}" dur="18s" begin="6s" repeatCount="indefinite"'
    c = LEAF_COLORS[1]
    fall = (f'<g transform="translate({cx} {mouth})"><g opacity="0">'
            f'<animate attributeName="opacity" values="0;1;1;1;0;0" keyTimes="0;.03;.4;.52;.6;1" dur="18s" begin="6s" repeatCount="indefinite"/>'
            f'<animateTransform attributeName="transform" type="translate" values="-26 -60;-10 -32;-30 -4;6 26;30 {base - 3 - mouth};30 {base - 3 - mouth}" {spl}/>'
            f'<g><animateTransform attributeName="transform" type="scale" values="1 1;1 1;1 1;1 1;1 .35;1 .35" {spl}/>'
            f'<g><animateTransform attributeName="transform" type="rotate" values="0;50;-25;60;95;95" {spl}/>'
            f'<use href="#vleaf" transform="scale(1.1)" fill="{c}"/></g></g></g></g>')
    return sprig + body, fall


def shelf_card(theme, d):
    """Languages as a shelf of books: each language is a run of matching volumes, as many as its share of the code
    (one at least), titled on the first spine.  A bookend and a vase of maple close the row."""
    p = PAL[theme]
    W, H = 1200, 336
    rnd = random.Random(7)
    langs = d["langs"]
    N, X0, X1 = 34, 60, 1046
    raw = [s * N for _, s, _ in langs]
    counts = [max(1, int(r)) for r in raw]
    while langs and sum(counts) < N:          # largest remainder
        i = max(range(len(raw)), key=lambda i: raw[i] - counts[i])
        counts[i] += 1
    while sum(counts) > N:
        i = max((i for i in range(len(raw)) if counts[i] > 1), key=lambda i: counts[i] - raw[i])
        counts[i] -= 1
    vols = []
    for si, ((name, _, color), n) in enumerate(zip(langs, counts)):
        cloth = mix(color or p["langs"][si % len(p["langs"])], "#6b4a2b", .28)   # dyed book cloth, not screen colour
        cloth = mix(cloth, "#000", float(p["clothDim"]))
        bw, bh = rnd.uniform(24, 31), rnd.uniform(146, 172)
        for k in range(n):   # a set, but no two volumes quite alike: worn, faded, a little taller or thinner
            vols.append({"si": si, "name": name, "first": k == 0, "w": bw * rnd.uniform(.84, 1.16),
                         "h": min(184, bh + rnd.uniform(-10, 10)), "cloth": cloth,
                         "c": mix(cloth, rnd.choice(("#000", "#fff")), rnd.uniform(0, .11))})
    gap = 1.2
    k = (X1 - X0 - gap * (len(vols) - 1)) / max(sum(v["w"] for v in vols), 1)
    pulled = set(rnd.sample(range(len(vols)), min(3, len(vols))))
    books, shadows, x = [], [], X0
    for i, v in enumerate(vols):
        w, h = v["w"] * k, v["h"]
        y = SHELF_Y - h
        foil = p["foil"] if luma(v["c"]) < .5 else p["foilDark"]
        title = ""
        # a long name is set smaller to fit between the head and foot trim, down to a size that still reads
        size = min(11, 11 * (h - 70) / text_width("outfit", v["name"], 11, .6))
        if v["first"] and w >= 18 and size >= 8.5:
            # spine titles read top to bottom; rotated, the glyphs sit to the right of the baseline
            title = (f'<text transform="translate({x + w / 2 - size * .36:.1f} {y + 32:.1f}) rotate(90)" class="t" font-size="{size:.1f}" '
                     f'letter-spacing="{size * .055:.2f}" fill="{foil}">{esc(v["name"])}</text>')
        body = (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="2" fill="{v["c"]}"/>'
                + spine_trim(v["si"] % 3, x, y, w, foil, not title) + title
                + f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="2" fill="url(#spine)"/>')
        if i in pulled:   # now and then somebody lifts a book to look at it, and puts it back
            dur, beg = rnd.uniform(16, 24), rnd.uniform(3, 14)
            body = (f'<g><animateTransform attributeName="transform" type="translate" values="0 0;0 0;0 -18;0 -18;0 0;0 0" '
                    f'keyTimes="0;.4;.47;.58;.65;1" calcMode="spline" keySplines="0 0 1 1;{EASE};0 0 1 1;{EASE};0 0 1 1" '
                    f'dur="{dur:.1f}s" begin="{beg:.1f}s" repeatCount="indefinite"/>{body}</g>')
        books.append(f'<g class="bk" style="animation-delay:{i * .035:.3f}s"><title>{esc(v["name"])}</title>{body}</g>')
        shadows.append(f'<rect x="{x + 3:.1f}" y="{y + 3:.1f}" width="{w:.1f}" height="{h - 3:.1f}" rx="2"/>')
        x += w + gap
    landed = len(vols) * .035 + .5
    grain = "".join(f'<path d="M44,{SHELF_Y + yy} C{300 + 80 * j},{SHELF_Y + yy - 2} {700 - 60 * j},{SHELF_Y + yy + 2.5} {W - 44},{SHELF_Y + yy}" '
                    f'fill="none" stroke="{p["woodLine"]}" stroke-opacity=".22" stroke-width=".8"/>' for j, yy in enumerate((4.5, 8, 11.5)))
    plank = (f'<rect x="44" y="{SHELF_Y + 15}" width="{W - 88}" height="30" fill="url(#wall)"/>'
             f'<rect x="44" y="{SHELF_Y - 4}" width="{W - 88}" height="5" fill="{p["wood"]}"/>'
             f'<rect x="44" y="{SHELF_Y}" width="{W - 88}" height="15" rx="2" fill="url(#wood)"/>{grain}'
             f'<rect x="44" y="{SHELF_Y}" width="{W - 88}" height="1.2" fill="#fff" opacity=".2"/>')
    bx = X1 + .5          # the bookend stands right against the last book, holding the row up
    bookend = (f'<rect x="{bx}" y="{SHELF_Y - 70}" width="8" height="70" rx="2.5" fill="url(#metal)"/>'
               f'<rect x="{bx + 1.6}" y="{SHELF_Y - 67}" width="1.3" height="62" fill="#fff" opacity=".25"/>')
    flowers, falling = vase(p, 1112, SHELF_Y - 2)
    legend, lx = [], 60
    for si, (name, share, _) in enumerate(langs):
        col = next(v["cloth"] for v in vols if v["si"] == si)
        pct = f"{share * 100:.1f}%"
        legend.append(f'<rect x="{lx}" y="{SHELF_Y + 45}" width="8" height="13" rx="1.5" fill="{col}"/>'
                      f'<rect x="{lx + 1}" y="{SHELF_Y + 48}" width="6" height="1.2" fill="{p["foil"]}" opacity=".8"/>'
                      f'<text x="{lx + 15}" y="{SHELF_Y + 56}" class="m" font-size="12"><tspan fill="{p["label"]}">{esc(name)}</tspan>'
                      f'<tspan fill="{p["muted"]}" dx="7">{pct}</tspan></text>')
        lx += 15 + text_width("jbmono", name, 12) + 7 + text_width("jbmono", pct, 12) + 30
    if not vols:
        books = [f'<text x="{W / 2}" y="{SHELF_Y - 60}" text-anchor="middle" class="m" font-size="13" fill="{p["muted"]}">no books on the shelf yet</text>']
    css = ("@keyframes drop{0%{opacity:0;transform:translateY(-30px)}70%{opacity:1;transform:translateY(2px)}100%{opacity:1;transform:none}}"
           ".bk{animation:drop .65s cubic-bezier(.3,.7,.4,1) both}"
           "@keyframes late{from{opacity:0}to{opacity:1}}.late{animation:late .8s ease both}")
    note = f"{len(langs)} languages · {d['repos']} public repos · by size of code"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="languages of {LOGIN} as a bookshelf">'
            + card_frame(p, W, H, "S")
            + f'<defs><style><![CDATA[{css}]]></style>{leaf_def("vleaf")}'
            f'<linearGradient id="spine" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#000" stop-opacity=".32"/>'
            f'<stop offset=".14" stop-color="#000" stop-opacity=".04"/><stop offset=".36" stop-color="#fff" stop-opacity=".15"/>'
            f'<stop offset=".6" stop-color="#fff" stop-opacity="0"/><stop offset=".86" stop-color="#000" stop-opacity=".12"/>'
            f'<stop offset="1" stop-color="#000" stop-opacity=".36"/></linearGradient>'
            f'<linearGradient id="wood" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{p["wood0"]}"/><stop offset="1" stop-color="{p["wood1"]}"/></linearGradient>'
            f'<linearGradient id="wall" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{p["wallShade"]}" stop-opacity="{p["wallShadeO"]}"/>'
            f'<stop offset="1" stop-color="{p["wallShade"]}" stop-opacity="0"/></linearGradient>'
            f'<linearGradient id="metal" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{p["metal0"]}"/><stop offset="1" stop-color="{p["metal1"]}"/></linearGradient>'
            f'<linearGradient id="vaseG" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{p["vase0"]}"/><stop offset=".4" stop-color="{p["vase0"]}"/>'
            f'<stop offset="1" stop-color="{p["vase1"]}"/></linearGradient>'
            f'<filter id="bshade" x="-50%" y="-10%" width="200%" height="120%"><feGaussianBlur stdDeviation="3"/></filter></defs>'
            + f'<g transform="translate(58 34)" fill="{p["accent"]}">{ICON["star"]}</g>'
            + f'<text x="76" y="40" class="t" font-size="19" fill="url(#tgS)">bookshelf</text>'
            + f'<text x="{W - 48}" y="40" class="m" font-size="12" text-anchor="end" fill="{p["label"]}">{note}</text>'
            + f'<g class="late" style="animation-delay:{landed:.2f}s"><g fill="{p["bookShade"]}" opacity="{p["bookShadeO"]}" filter="url(#bshade)">{"".join(shadows)}</g></g>'
            + "".join(books) + flowers + bookend + plank + falling + "".join(legend) + "</svg>")


# the contents page's bottom-right corner curls up: (px along the bottom edge, px up the right edge) at rest,
# and when it lifts as if about to be turned
CURL_REST, CURL_LIFT = (86, 68), (112, 90)


def curl_geometry(W, H, a, b):
    """Path data and gradient axis for the corner folded back along the crease from (W-a, H) to (W, H-b).
    The flap is the corner mirrored over the crease, its edges bowed and its tip rounded like the card's corners;
    the crease itself bulges toward the corner, where the paper rolls over."""
    def lerp(A, B, t):
        return (A[0] + (B[0] - A[0]) * t, A[1] + (B[1] - A[1]) * t)

    def toward(A, B, dist):
        length = ((B[0] - A[0]) ** 2 + (B[1] - A[1]) ** 2) ** .5
        return lerp(A, B, dist / length)

    P1, P2, C = (W - a, H), (W, H - b), (W, H)
    dx, dy = P2[0] - P1[0], P2[1] - P1[1]
    t = ((C[0] - P1[0]) * dx + (C[1] - P1[1]) * dy) / (dx * dx + dy * dy)
    F = (P1[0] + t * dx, P1[1] + t * dy)             # foot of the corner on the crease
    T = (2 * F[0] - C[0], 2 * F[1] - C[1])           # where the corner's tip lands
    Q = lerp(F, C, .3)                               # crease control point
    A, B = toward(T, P1, 16), toward(T, P2, 16)
    c1, c2 = lerp(lerp(P1, A, .5), F, .18), lerp(lerp(B, P2, .5), F, .18)
    mid = lerp(lerp(P2, Q, .5), lerp(Q, P1, .5), .5)  # middle of the crease curve
    pt = lambda P: f"{P[0]:.1f},{P[1]:.1f}"
    return {
        "clip": f"M0,0 H{W} V{P2[1]:.1f} Q{pt(Q)} {pt(P1)} H0 Z",
        "flap": f"M{pt(P1)} Q{pt(c1)} {pt(A)} Q{pt(T)} {pt(B)} Q{pt(c2)} {pt(P2)} Q{pt(Q)} {pt(P1)} Z",
        "crease": f"M{pt(P2)} Q{pt(Q)} {pt(P1)}",
        "x1": f"{mid[0]:.1f}", "y1": f"{mid[1]:.1f}", "x2": f"{T[0]:.1f}", "y2": f"{T[1]:.1f}",
    }


def page_curl(W, H, p):
    """(defs, under, over) for a curled bottom-right corner: `under` is the next page showing through, drawn before
    the card; the card goes in <g clip-path="url(#curl)">; `over` is the flap and its shadow.  Every ten seconds
    the corner lifts a little, as if about to be turned, and settles back."""
    frames = [curl_geometry(W, H, *ab) for ab in (CURL_REST, CURL_REST, CURL_LIFT, CURL_REST, CURL_REST)]
    rest = frames[0]
    timing = (f'keyTimes="0;.5;.64;.82;1" calcMode="spline" keySplines="0 0 1 1;{EASE};{EASE};0 0 1 1" '
              f'dur="10s" begin="3s" repeatCount="indefinite"')

    def anim(attr, key=None):
        return f'<animate attributeName="{attr}" values="{";".join(f[key or attr] for f in frames)}" {timing}/>'

    stops = zip((0, .12, .45, 1), (p["flap0"], p["flap1"], p["flap2"], p["flap3"]))
    defs = (f'<clipPath id="curl"><path d="{rest["clip"]}">{anim("d", "clip")}</path></clipPath>'
            f'<linearGradient id="flapG" gradientUnits="userSpaceOnUse" x1="{rest["x1"]}" y1="{rest["y1"]}" x2="{rest["x2"]}" y2="{rest["y2"]}">'
            + "".join(f'<stop offset="{o}" stop-color="{c}"/>' for o, c in stops)
            + anim("x1") + anim("y1") + anim("x2") + anim("y2") + '</linearGradient>'
            f'<filter id="curlBlur" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="5"/></filter>')
    under = (f'<rect x="0.75" y="0.75" width="{W - 1.5}" height="{H - 1.5}" rx="16" fill="{p["nextPage"]}" stroke="{p["border"]}" stroke-width="1.5"/>'
             # the roll shades the next page along the crease
             f'<path d="{rest["crease"]}" fill="none" stroke="#000" stroke-width="12" opacity="{p["curlShadeO"]}" filter="url(#curlBlur)">{anim("d", "crease")}</path>')
    over = (f'<path d="{rest["flap"]}" transform="translate(-4 -4)" fill="#000" opacity="{p["curlShadeO"]}" filter="url(#curlBlur)">{anim("d", "flap")}</path>'
            f'<path d="{rest["flap"]}" fill="url(#flapG)" stroke="{p["border"]}" stroke-opacity=".5" stroke-linejoin="round">{anim("d", "flap")}</path>')
    return defs, under, over


ROMAN = "i ii iii iv v vi vii viii ix x".split()


def toc_entry(p, x0, x1, y, num, name, value, sub, t):
    """One contents line: numeral, title, dot leaders running out to the value, and a note underneath.
    Fades in at t; the leaders' base length is the finished line, the set at 0s shortens it until they run out."""
    nx = x0 + 36
    vw = text_width("jbmono", value, 13)
    name = clip_text("outfit", name, 21, x1 - vw - 40 - nx)
    nw = text_width("outfit", name, 21)
    lx0, lx1 = nx + nw + 10, x1 - vw - 10
    sub = clip_text("jbmono", sub, 11.5, x1 - nx)
    leader = ""
    if lx1 > lx0 + 8:
        leader = (f'<line x1="{lx0:.1f}" y1="{y - 5}" x2="{lx1:.1f}" y2="{y - 5}" stroke="{p["muted"]}" stroke-width="1.8" '
                  f'stroke-linecap="round" stroke-dasharray="0 7"><set attributeName="x2" to="{lx0:.1f}" begin="0s" fill="freeze"/>'
                  f'<animate attributeName="x2" from="{lx0:.1f}" to="{lx1:.1f}" begin="{t + .25:.2f}s" dur=".7s" fill="freeze"/></line>')
    return (f'<g class="e" style="animation-delay:{t:.2f}s">'
            f'<text x="{x0 + 24}" y="{y}" text-anchor="end" class="h" font-size="28" fill="{p["accent"]}">{ROMAN[num]}.</text>'
            f'<text x="{nx}" y="{y}" class="t" font-size="21" fill="{p["value"]}">{esc(name)}</text>'
            f'<text x="{x1}" y="{y}" class="m" font-size="13" text-anchor="end" fill="{p["label"]}">{esc(value)}</text>'
            f'<text x="{nx}" y="{y + 21}" class="m" font-size="11.5" fill="{p["muted"]}">{esc(sub)}</text></g>' + leader, nx, nw)


BLOSSOM_PETAL = "M0,0 C-3.3,-2.4 -3.5,-6.6 -1.3,-8.2 L0,-6.9 L1.3,-8.2 C3.5,-6.6 3.3,-2.4 0,0 Z"   # notched at the tip


def preface_icon(kind, p):
    """Little drawn stand-ins for the prologue's emoji, about 20px across, centred on the origin."""
    line = f'fill="none" stroke="{p["accent"]}" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"'
    if kind == "cap":         # mortarboard with its tassel
        return (f'<g {line}><path d="M0,-6.5 L10,-2.5 L0,1.5 L-10,-2.5 Z" fill="{p["accent"]}" fill-opacity=".25"/>'
                f'<path d="M-5.5,-.3 V4 Q0,7.5 5.5,4 V-.3"/><path d="M10,-2.5 V4.5"/></g>'
                f'<circle cx="10" cy="5.6" r="1.5" fill="{p["accent"]}"/>')
    if kind == "books":       # two standing, one leaning
        return (f'<g {line}><rect x="-8" y="-6.5" width="4.4" height="13" rx=".8"/><rect x="-2.6" y="-4.5" width="4.4" height="11" rx=".8"/>'
                f'<rect x="2.6" y="-6.5" width="4.4" height="13" rx=".8" transform="rotate(14 7 6.5)"/><path d="M-9.5,6.5 H10.5"/></g>')
    petals = "".join(f'<path d="{BLOSSOM_PETAL}" transform="rotate({a})"/>' for a in range(0, 360, 72))
    return f'<g fill="{p["blossom"]}">{petals}</g><circle r="1.7" fill="{p["accent"]}"/>'   # cherry blossom


def wrap(key, text, size, max_w):
    """Break `text` into lines no wider than max_w."""
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if cur and text_width(key, trial, size) > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    return lines + [cur] if cur else lines


def preface_page(p, x0, x1, y0, t0):
    """The preface lines, hand-written one after another from t0: each line is uncovered left to right at
    writing speed (its clip's base width shows the whole line, the set at 0s hides it until the pen gets there).
    Returns (body, clip defs, last baseline)."""
    tx, size, lead, gap, speed = x0 + 36, 27, 31, 17, 280
    body, clips, y, t = [], [], y0, t0
    for i, (icon, text) in enumerate(PREFACE):
        body.append(f'<g class="e" style="animation-delay:{t:.2f}s"><g transform="translate({x0 + 14} {y - 8})">{preface_icon(icon, p)}</g></g>')
        lines = [ln for part in text.split("\n") for ln in wrap("caveat", part, size, x1 - tx)]
        for j, line in enumerate(lines):
            w = text_width("caveat", line, size) + 14
            dur = max(.3, w / speed)
            ink = esc(line)
            for name in PREFACE_NAMES:
                ink = ink.replace(esc(name), f'<tspan fill="{p["accent"]}">{esc(name)}</tspan>')
            clips.append(f'<clipPath id="pw{i}_{j}"><rect x="{tx - 6}" y="{y - size - 4}" width="{w:.1f}" height="{size + 16}">'
                         f'<set attributeName="width" to="0" begin="0s" fill="freeze"/>'
                         f'<animate attributeName="width" from="0" to="{w:.1f}" begin="{t:.2f}s" dur="{dur:.2f}s" fill="freeze"/></rect></clipPath>')
            body.append(f'<text x="{tx}" y="{y}" class="h" font-size="{size}" fill="{p["value"]}" clip-path="url(#pw{i}_{j})">{ink}</text>')
            t += dur + .08
            y += lead
        y += gap
    return "".join(body), "".join(clips), y - lead - gap


def toc_card(theme, d):
    """A book lying open: the preface on the left page (see PREFACE) and the contents - my own repositories,
    latest first - on the right.  A ribbon lies in the gutter; the bottom-right corner is curled."""
    p = PAL[theme]
    W = 1200
    today = d["today"]

    def when(day):
        m = day.strftime("%b").lower()
        return f"{m} {day.day}" if day.year == today.year else f"{m} {day.year}"

    chapters = []
    for r in d["own"][:4]:
        about = [r["langs"][0], r["desc"]] if r["desc"] and r["langs"] else [r["desc"] or ", ".join(r["langs"][:3])]
        chapters.append((r["name"], when(r["pushed"]), "  ·  ".join(a for a in about if a)))
    Y0, PITCH = 168, 58
    (lx0, lx1), (rx0, rx1) = (96, 552), (648, 1104)
    preface, preface_clips, preface_end = preface_page(p, lx0, lx1, Y0, .3)
    contents_end = Y0 + (max(len(chapters), 1) - 1) * PITCH + 21
    H = round(max(preface_end, contents_end) + 70)
    body = []
    for pi, (x0, x1, title, part, col) in enumerate([(lx0, lx1, "Preface", "about the author", ""),
                                                     (rx0, rx1, "Contents", "my repositories", "last pushed")]):
        body.append(f'<text x="{x0}" y="84" class="h" font-size="46" fill="url(#tgT)">{title}</text>'
                    f'<text x="{x0}" y="118" class="m" font-size="12" letter-spacing="2" fill="{p["accent"]}">{part}</text>'
                    f'<text x="{x1}" y="118" class="m" font-size="11" text-anchor="end" fill="{p["muted"]}">{col}</text>'
                    f'<rect x="{x0}" y="131" width="{x1 - x0}" height="1.2" fill="url(#rule)"/>'
                    f'<text x="{(x0 + x1) / 2}" y="{H - 26}" text-anchor="middle" class="h" font-size="20" fill="{p["muted"]}">~ {pi + 1} ~</text>')
    body.append(preface)
    if not chapters:
        body.append(f'<text x="{rx0 + 36}" y="{Y0}" class="h" font-size="24" fill="{p["muted"]}">blank pages, for now</text>')
    latest = None
    for j, (name, value, sub) in enumerate(chapters):
        y = Y0 + j * PITCH
        entry, nx, nw = toc_entry(p, rx0, rx1, y, j, name, value, sub, .5 + j * .18)
        body.append(entry)
        latest = latest or (nx, nw, y)
    underline = ""
    if latest:   # a red-pencil underline under the latest chapter, once the contents are written
        nx, nw, y = latest
        underline = (f'<path d="M{nx - 3:.1f},{y + 7} C{nx + nw * .3:.1f},{y + 3} {nx + nw * .65:.1f},{y + 10} {nx + nw + 5:.1f},{y + 4.5}" '
                     f'fill="none" stroke="{p["ribbon0"]}" stroke-width="2.4" stroke-linecap="round" opacity=".85" pathLength="1" stroke-dasharray="1 1">'
                     f'<set attributeName="stroke-dashoffset" to="1" begin="0s" fill="freeze"/>'
                     f'<animate attributeName="stroke-dashoffset" from="1" to="0" begin="{.5 + len(chapters) * .18 + .6:.2f}s" dur=".6s" fill="freeze"/></path>')
    gut = "".join(f'<stop offset="{i / 10:.1f}" stop-color="{p["gutter"]}" stop-opacity="{float(p["gutterO"]) * (3 * b * b - 2 * b ** 3):.3f}"/>'
                  for i in range(11) for b in [1 - abs(2 * i / 10 - 1)])
    L = 232
    ribbon = (f'<g transform="translate(600 0)"><g>'
              f'<animateTransform attributeName="transform" type="rotate" values="-1.4;1.4;-1.4" keyTimes="0;.5;1" calcMode="spline" '
              f'keySplines="{EASE};{EASE}" dur="7s" repeatCount="indefinite"/>'
              f'<path d="M-8,-2 H10 V{L + 2} L1,{L - 9} L-8,{L + 2} Z" transform="translate(3 3)" fill="#000" opacity="{p["ribbonShadeO"]}" filter="url(#rblur)"/>'
              f'<path d="M-9,-2 H9 V{L} L0,{L - 11} L-9,{L} Z" fill="url(#rib)"/>'
              f'<path d="M-4,0 V{L - 7}" stroke="#fff" stroke-opacity=".2" stroke-width="1.5"/></g></g>')
    css = (fontface("caveat") + ".h{font-family:'Caveat',cursive;font-weight:600}"
           "@keyframes rise{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}.e{animation:rise .6s ease both}")
    curl_defs, next_page, flap = page_curl(W, H, p)
    label = esc(f"preface: {' '.join(text.replace(chr(10), ' ') for _, text in PREFACE)} contents: repositories of {LOGIN}")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="{label}">'
            + f'<defs>{curl_defs}</defs>' + next_page + '<g clip-path="url(#curl)">'
            + card_frame(p, W, H, "T")
            + f'<defs><style><![CDATA[{css}]]></style>{preface_clips}'
            f'<linearGradient id="gut" x1="0" y1="0" x2="1" y2="0">{gut}</linearGradient>'
            f'<linearGradient id="rule" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{p["accent"]}" stop-opacity=".7"/><stop offset="1" stop-color="{p["accent"]}" stop-opacity="0"/></linearGradient>'
            f'<linearGradient id="rib" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{p["ribbon1"]}"/><stop offset=".35" stop-color="{p["ribbon0"]}"/>'
            f'<stop offset="1" stop-color="{p["ribbon1"]}"/></linearGradient>'
            f'<filter id="rblur" x="-50%" y="-10%" width="200%" height="120%"><feGaussianBlur stdDeviation="2.5"/></filter></defs>'
            + f'<rect x="540" y="1.5" width="120" height="{H - 3}" fill="url(#gut)"/>'
            + f'<line x1="600" y1="1.5" x2="600" y2="{H - 1.5}" stroke="{p["gutter"]}" stroke-opacity="{p["gutterO"]}"/>'
            + "".join(body) + underline + ribbon + "</g>" + flap + "</svg>")


WORKS_MAX = 4              # volumes on the works-in-progress ledge
COVER_W, COVER_H = 196, 278    # A6, a bunkobon; the readme column shows cards at ~.7 scale, so no smaller
LEDGE_Y = 366              # where the covers stand
IMPRINT = "shxiao bunko"   # the publisher's name at the foot of every jacket
FRESH_DAYS = 30            # pushed this recently, the cover wears a "new chapter" sticker
LEAD = 1.12                # title line spacing, in ems
CAP = .72                  # Outfit's cap height, in ems


def title_lines(name, max_w, max_h, max_lines=3):
    """A repository name set as a cover title, as large as fits in max_lines lines and max_h px from the first
    line's cap height to the last baseline: broken after - _ . or between camelCase words, never inside one.
    Returns (size, lines)."""
    parts = re.split(r"(?<=[-_.])(?=[^-_.])|(?<=[a-z0-9])(?=[A-Z])", name)
    for size in range(26, 13, -1):
        lines = [""]
        for part in parts:
            if lines[-1] and text_width("outfit", lines[-1] + part, size) > max_w:
                lines.append("")
            lines[-1] += part
        if (len(lines) <= max_lines and (len(lines) - 1) * size * LEAD + size * CAP <= max_h
                and all(text_width("outfit", ln, size) <= max_w for ln in lines)):
            return size, lines
    return size, [clip_text("outfit", ln, size, max_w) for ln in lines[:max_lines - 1]] + \
        [clip_text("outfit", "".join(lines[max_lines - 1:]), size, max_w)]


def obi_line(v):
    """The obi's catch line."""
    if v["stars"]:
        return f"loved by {v['stars']} reader{'s' if v['stars'] != 1 else ''}"
    return "a quiet little story"


WIDE = "[\u2e80-\u9fff\uac00-\ud7af\uf900-\ufaff\ufe30-\ufe4f\uff00-\uffef]"   # CJK, hangul, full-width forms


def wrap_blurb(text, size, max_w):
    """Like wrap(), but CJK text (which has no spaces) may break between any two characters."""
    lines, cur = [], ""
    for tok in re.findall(WIDE + r"|[^\s" + WIDE[1:-1] + r"]+|\s+", text):
        if cur and not tok.isspace() and text_width("jbmono", cur + tok, size) > max_w:
            lines.append(cur.rstrip())
            cur = ""
        if cur or not tok.isspace():
            cur += " " if tok.isspace() else tok
    return lines + [cur.rstrip()] if cur.strip() else lines


def wash(p, v, i, shade, oy):
    """The cover art: a watercolour wash in the language's colour, laid on a diagonal from the lower left to the
    upper right with a few splatters, and cherry petals drifting down across it.  Seeded by the repository's name,
    so each volume keeps its picture from day to day."""
    cw = COVER_W
    rnd = random.Random(v["name"])
    base = mix(v["color"] or p["langs"][i % len(p["langs"])], "#000", shade)
    blobs = []
    for k in range(6):
        t = k / 5
        c = mix(base, rnd.choice(("#fff", "#000", p["paper"])), rnd.uniform(0, .45))
        if k == 3:
            c = mix(base, p["blossom"], .55)   # one wash of a second colour, as a painter would
        blobs.append(f'<ellipse cx="{20 + t * (cw - 40) + rnd.uniform(-18, 18):.0f}" cy="{oy - 24 - t * (oy - 80) + rnd.uniform(-16, 16):.0f}" '
                     f'rx="{rnd.uniform(38, 70):.0f}" ry="{rnd.uniform(28, 52):.0f}" fill="{c}" opacity="{rnd.uniform(.4, .75):.2f}"/>')
    dots = "".join(f'<circle cx="{rnd.uniform(8, cw - 8):.0f}" cy="{rnd.uniform(30, oy - 6):.0f}" r="{rnd.uniform(.6, 2.2):.1f}"/>'
                   for _ in range(14))
    petals = []
    for k in range(2):
        x0, dur, beg = rnd.uniform(30, cw - 60), rnd.uniform(11, 16), -rnd.uniform(0, 14)
        petals.append(f'<g><animateTransform attributeName="transform" type="translate" values="{x0:.0f} -12;{x0 + 40:.0f} {oy / 2:.0f};{x0 + 10:.0f} {oy + 10}" '
                      f'dur="{dur:.1f}s" begin="{beg:.1f}s" repeatCount="indefinite"/>'
                      f'<path d="{BLOSSOM_PETAL}" transform="scale(1.5)" fill="{p["blossom"]}" opacity=".85">'
                      f'<animateTransform attributeName="transform" type="rotate" values="0;200;360" additive="sum" dur="{dur:.1f}s" begin="{beg:.1f}s" repeatCount="indefinite"/></path></g>')
    return (f'<g filter="url(#wash)">{"".join(blobs)}</g><g fill="{base}" opacity=".45">{dots}</g>'
            + "".join(petals))


def cover(p, i, v, today, shade=0):
    """One bunkobon face out, drawn at the origin: an A6 paperback in a paper jacket with a watercolour on it,
    the title set vertically in a label at the top right with the author beneath, the catalogue number at the top
    left and the imprint at the foot, and an obi carrying the description as the blurb.  A glint of light crosses
    the jacket now and then.  `shade` darkens the wash, so two volumes in one language aren't twins."""
    cw, ch = COVER_W, COVER_H
    ink, halo = p["ink"], f'stroke="{p["paper"]}" stroke-width="3" stroke-linejoin="round" paint-order="stroke"'
    oy = round(ch * .64)         # top of the obi
    # the title label: columns read top to bottom, the first on the right; rotated, glyphs sit right of the baseline
    right, top = cw - 14, 14
    size, cols = title_lines(v["name"], oy - 64, 62)
    lead = size * LEAD
    bx = [right - 9 - size * CAP - j * lead for j in range(len(cols))]
    owner = clip_text("jbmono", v["owner"], 10, oy - 64)
    ax = bx[-1] - size * .25 - 6 - 10 * CAP        # the author's column, left of the title
    left = ax - 9
    lh = max([text_width("outfit", c, size) for c in cols] + [text_width("jbmono", owner, 10) + 30]) + 22
    label = (f'<rect x="{left:.1f}" y="{top}" width="{right - left:.1f}" height="{lh:.1f}" fill="{p["paper"]}" opacity=".94"/>'
             f'<rect x="{left + 3:.1f}" y="{top + 3}" width="{right - left - 6:.1f}" height="{lh - 6:.1f}" fill="none" stroke="{ink}" stroke-opacity=".35" stroke-width=".6"/>'
             + "".join(f'<text transform="translate({x:.1f} {top + 11}) rotate(90)" class="t" font-size="{size}" fill="{ink}">{esc(c)}</text>'
                       for x, c in zip(bx, cols))
             + f'<text transform="translate({ax:.1f} {top + lh - 11:.1f}) rotate(90)" text-anchor="end" class="m" font-size="10" '
               f'letter-spacing="1" fill="{p["inkMuted"]}">{esc(owner)}</text>')
    jacket = (f'<rect width="{cw}" height="{ch}" rx="2" fill="{p["paper"]}"/>'
              + wash(p, v, i, shade, oy) +
              f'<rect width="{cw}" height="{ch}" filter="url(#paperG)" opacity=".07"/>'
              f'<path d="M7,0 V{ch}" stroke="#000" stroke-opacity=".06"/><path d="M8.2,0 V{ch}" stroke="#fff" stroke-opacity=".18"/>'   # the scored fold by the spine
              + label +
              f'<text x="16" y="26" class="m" font-size="10" fill="{p["inkMuted"]}" {halo}>{esc(v["owner"][:1].lower())}-1-{i + 1}</text>'
              f'<text x="16" y="46" class="h" font-size="18" fill="{ink}" {halo}>vol. {ROMAN[i]}</text>'
              f'<g transform="translate(23 {oy - 16})"><circle r="7.5" fill="{p["paper"]}" stroke="{ink}" stroke-width="1"/>'
              f'<path d="{star_path(4)}" fill="{ink}"/></g>'
              f'<text x="35" y="{oy - 12.5}" class="m" font-size="9" letter-spacing=".5" fill="{ink}" {halo}>{esc(IMPRINT)}</text>'
              f'<rect width="{cw}" height="{oy}" fill="#000" opacity="{p["coverDim"]}"/>'
              f'<rect width="{cw}" height="{ch}" rx="2" fill="url(#board)"/>')
    cx = cw / 2
    head = clip_text("caveat", obi_line(v), 22, cw - 16)
    bw, bs = cw - 30, 12
    blurb = wrap_blurb(v["desc"], bs, bw) or ["(no blurb yet)"]
    if len(blurb) > 2:
        blurb = [blurb[0], clip_text("jbmono", blurb[1].rstrip(" ,.;:-，。、") + "...", bs, bw)]
    forks = f"{v['forks']} fork{'s' if v['forks'] != 1 else ''}"
    fw = text_width("jbmono", forks, 10.5)
    sticker = ""
    if (today - v["pushed"]).days <= FRESH_DAYS:   # a shop sticker on the jacket: still being written
        sticker = (f'<g transform="translate(42 {round(ch * .45)}) rotate(-12)"><circle r="23" fill="{p["obiInk"]}"/>'
                   f'<circle r="20" fill="none" stroke="{p["obi"]}" stroke-opacity=".6" stroke-dasharray="2 2"/>'
                   f'<text y="1" text-anchor="middle" class="h" font-size="18" fill="{p["obi"]}">new</text>'
                   f'<text y="11" text-anchor="middle" class="m" font-size="7" letter-spacing=".4" fill="{p["obi"]}">chapter</text></g>')
    obi = (f'<path d="M0,{oy} H{cw} V{ch - 2} Q{cw},{ch} {cw - 2},{ch} H2 Q0,{ch} 0,{ch - 2} Z" fill="{p["obi"]}"/>'
           f'<path d="M7,{oy} V{ch}" stroke="#000" stroke-opacity=".06"/>'
           f'<rect y="{oy}" width="{cw}" height="1" fill="#fff" opacity=".5"/>'
           f'<text x="{cx}" y="{oy + 27}" text-anchor="middle" class="h" font-size="22" fill="{p["obiInk"]}">{esc(head)}</text>'
           f'<rect x="{cx - 18}" y="{oy + 35}" width="36" height="1" fill="{p["obiInk"]}" opacity=".45"/>'
           + "".join(f'<text x="{cx}" y="{oy + 54 + j * 17}" text-anchor="middle" class="m" font-size="{bs}" fill="{p["obiText"]}">{esc(ln)}</text>'
                     for j, ln in enumerate(blurb)) +
           f'<text x="15" y="{ch - 12}" class="m" font-size="10.5" fill="{p["obiMuted"]}">{esc(clip_text("jbmono", v["lang"], 10.5, bw - fw - 16))}</text>'
           f'<text x="{cw - 14}" y="{ch - 12}" text-anchor="end" class="m" font-size="10.5" fill="{p["obiMuted"]}">{forks}</text>')
    glint = (f'<g transform="translate(-120 0)">'
             f'<animateTransform attributeName="transform" type="translate" values="-120 0;-120 0;300 0;300 0" keyTimes="0;.84;.93;1" '
             f'calcMode="spline" keySplines="0 0 1 1;{EASE};0 0 1 1" dur="15s" begin="{3 + i * 1.6:.1f}s" repeatCount="indefinite"/>'
             f'<rect y="-20" width="70" height="{ch + 40}" transform="skewX(-18)" fill="url(#glint)"/></g>')
    about = f"{v['name']}: {v['desc']}" if v["desc"] else v["name"]
    return (f'<clipPath id="wc{i}"><rect width="{cw}" height="{ch}" rx="2"/></clipPath>',
            f'<title>{esc(about)}</title><g clip-path="url(#wc{i})">{jacket}{sticker}{obi}{glint}</g>')


def works_card(theme, d):
    """Chapter ii: the pinned repositories (or, until some are pinned, the most starred) as bunkobon face out on a
    ledge, like new paperbacks in a shop window, each wearing an obi with its description as the blurb."""
    p = PAL[theme]
    W, H = 1200, 430
    vols = d["works"]
    rnd = random.Random(5)
    gap = 56
    x = (60 + W - 48) / 2 - (len(vols) * COVER_W + (len(vols) - 1) * gap) / 2
    y = LEDGE_Y - COVER_H
    clips, covers, shadows = [], [], []
    for i, v in enumerate(vols):
        twins = sum(1 for u in vols[:i] if u["lang"] == v["lang"])
        clip, body = cover(p, i, v, d["today"], .14 * twins)
        tilt = rnd.uniform(-1.2, 1.2)     # propped up by hand, not quite square
        clips.append(clip)
        covers.append(f'<g transform="translate({x:.1f} {y}) rotate({tilt:.2f} {COVER_W / 2} {COVER_H})">'
                      f'<g class="cv" style="animation-delay:{.2 + i * .18:.2f}s">{body}</g></g>')
        shadows.append(f'<rect x="{x + 7:.1f}" y="{y + 6}" width="{COVER_W}" height="{COVER_H - 6}" rx="2" transform="rotate({tilt:.2f} {x + COVER_W / 2:.1f} {LEDGE_Y})"/>')
        x += COVER_W + gap
    if not vols:
        covers = [f'<text x="{W / 2}" y="{LEDGE_Y - 110}" text-anchor="middle" class="h" font-size="26" fill="{p["muted"]}">nothing on the ledge yet</text>']
    landed = .2 + len(vols) * .18 + .6
    grain = "".join(f'<path d="M44,{LEDGE_Y + yy} C{300 + 80 * j},{LEDGE_Y + yy - 1.5} {700 - 60 * j},{LEDGE_Y + yy + 2} {W - 44},{LEDGE_Y + yy}" '
                    f'fill="none" stroke="{p["woodLine"]}" stroke-opacity=".22" stroke-width=".8"/>' for j, yy in enumerate((3, 9)))
    # a picture ledge: the covers stand in its groove, behind the front lip
    ledge = (f'<rect x="44" y="{LEDGE_Y + 12}" width="{W - 88}" height="30" fill="url(#wall)"/>'
             f'<rect x="44" y="{LEDGE_Y - 6}" width="{W - 88}" height="18" rx="2" fill="url(#wood)"/>{grain}'
             f'<rect x="44" y="{LEDGE_Y - 6}" width="{W - 88}" height="1.2" fill="#fff" opacity=".22"/>'
             f'<rect x="44" y="{LEDGE_Y + 10}" width="{W - 88}" height="2" fill="{p["woodLine"]}" opacity=".35"/>')
    css = (fontface("caveat") + ".h{font-family:'Caveat',cursive;font-weight:600}"
           "@keyframes up{from{opacity:0;transform:translateY(28px)}to{opacity:1;transform:none}}"
           ".cv{animation:up .8s cubic-bezier(.3,.7,.4,1) both}"
           "@keyframes late{from{opacity:0}to{opacity:1}}.late{animation:late .8s ease both}")
    what = "pinned repositories" if d["works_pinned"] else "most starred repositories"
    note = f"{len(vols)} volume{'s' if len(vols) != 1 else ''} · {what}"
    label = esc(f"works in progress: {', '.join(v['name'] for v in vols) or 'none yet'}")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="{label}">'
            + card_frame(p, W, H, "W")
            + f'<defs><style><![CDATA[{css}]]></style>{"".join(clips)}'
            f'<linearGradient id="board" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".12"/>'
            f'<stop offset=".45" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".14"/></linearGradient>'
            # watercolour: ragged, bleeding edges; and the jacket paper's grain
            f'<filter id="wash" x="-30%" y="-30%" width="160%" height="160%"><feTurbulence type="fractalNoise" baseFrequency=".035" numOctaves="3" seed="4"/>'
            f'<feDisplacementMap in="SourceGraphic" scale="30" xChannelSelector="R" yChannelSelector="G"/><feGaussianBlur stdDeviation="3"/></filter>'
            f'<filter id="paperG" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency=".9" numOctaves="2" stitchTiles="stitch"/>'
            f'<feColorMatrix type="saturate" values="0"/></filter>'
            f'<linearGradient id="glint" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/>'
            f'<stop offset=".5" stop-color="#fff" stop-opacity="{p["glintO"]}"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
            f'<linearGradient id="wood" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{p["wood0"]}"/><stop offset="1" stop-color="{p["wood1"]}"/></linearGradient>'
            f'<linearGradient id="wall" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{p["wallShade"]}" stop-opacity="{p["wallShadeO"]}"/>'
            f'<stop offset="1" stop-color="{p["wallShade"]}" stop-opacity="0"/></linearGradient>'
            f'<filter id="wshade" x="-20%" y="-10%" width="140%" height="120%"><feGaussianBlur stdDeviation="5"/></filter></defs>'
            + f'<g transform="translate(58 34)" fill="{p["accent"]}">{ICON["star"]}</g>'
            + f'<text x="76" y="40" class="t" font-size="19" fill="url(#tgW)">works in progress</text>'
            + f'<text x="{W - 48}" y="40" class="m" font-size="12" text-anchor="end" fill="{p["label"]}">{note}</text>'
            + f'<g class="late" style="animation-delay:{landed:.2f}s"><g fill="{p["bookShade"]}" opacity="{p["bookShadeO"]}" filter="url(#wshade)">{"".join(shadows)}</g></g>'
            + "".join(covers) + ledge + "</svg>")


def snake_card(theme, raw, d):
    """The contributions card: snk's svg nested in a card like the others, scaled up to 16px cells on a 20px pitch.
    No total in the header: the stats panel already gives the all-time one, and a 12-month total beside it never
    quite agrees.  Only fonts and .t/.m go in the style block; snk's own css uses .c/.s/.u."""
    p = PAL[theme]
    W, H = 1200, 300
    vb = re.search(r'viewBox="([^"]+)"', raw).group(1)
    vx, vy, vw, vh = map(float, vb.split())
    inner = raw[raw.index(">", raw.index("<svg")) + 1:raw.rindex("</svg>")]
    scale = 20 / 16               # snk: 12px cells on a 16px pitch
    gx, gy = 48, 78               # top-left of the grid
    css = (fontface("outfit") + fontface("jbmono") +
           ".t{font-family:'Outfit',sans-serif;font-weight:800}"
           ".m{font-family:'JetBrains Mono',monospace;font-weight:500}")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="contribution snake of {LOGIN}">'
            f'<defs><style><![CDATA[{css}]]></style>'
            f'<linearGradient id="bgN" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{p["bg0"]}"/><stop offset="1" stop-color="{p["bg1"]}"/></linearGradient>'
            f'<linearGradient id="tgN" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{p["grad0"]}"/><stop offset="1" stop-color="{p["grad1"]}"/></linearGradient>'
            f'</defs>'
            f'<rect x="0.75" y="0.75" width="{W-1.5}" height="{H-1.5}" rx="16" fill="url(#bgN)" stroke="{p["border"]}" stroke-width="1.5"/>'
            f'<g transform="translate(58 34)" fill="{p["accent"]}">{ICON["star"]}</g>'
            f'<text x="76" y="40" class="t" font-size="19" fill="url(#tgN)">contributions</text>'
            f'<text x="{W-gx}" y="40" class="m" font-size="12" text-anchor="end" fill="{p["label"]}">{d["active_days"]} active days · last 12 months</text>'
            f'<svg x="{gx + vx*scale:.1f}" y="{gy + vy*scale:.1f}" width="{vw*scale:.1f}" height="{vh*scale:.1f}" viewBox="{vb}">{inner}</svg>'
            f'</svg>')


def wrap_snake(d):
    for theme in ("dark", "light"):
        path = os.path.join(OUT, f"snake-{theme}.svg")
        if not os.path.exists(path):
            print(f"no {path} (Platane/snk runs first in Actions); contributions card skipped")
            continue
        raw = open(path, encoding="utf-8").read()
        if 'aria-label="contribution snake of' in raw:
            continue
        write_svg(path, punch(snake_card(theme, raw, d), theme == "dark"))
        print(f"framed {path} ({os.path.getsize(path)//1024} KB)")


def main():
    os.makedirs(OUT, exist_ok=True)
    d = collect()
    wrap_snake(d)
    for theme in ("dark", "light"):
        for name, fn in (("stats", stats_panel), ("shelf", shelf_card), ("toc", toc_card), ("works", works_card)):
            path = os.path.join(OUT, f"{name}-{theme}.svg")
            svg = fn(theme, d)
            if name != "toc":   # the contents page is a book page, with a curled corner instead of binder holes
                # the shelf's holes go down the right edge, past the vase, so the row of books starts on a clean edge
                svg = punch(svg, theme == "dark", side="right" if name == "shelf" else "left")
            write_svg(path, svg)
            print(f"wrote {path} ({os.path.getsize(path)//1024} KB)")
    print(json.dumps(d, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
