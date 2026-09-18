#!/usr/bin/env python3
"""Render the profile's stats panel, contribution calendar, bookshelf and contents page as themed SVGs.

Runs in GitHub Actions (see .github/workflows/cards.yml) and writes dist/{stats,calendar,shelf,toc}-{dark,light}.svg.
`gen_cards.py snake` instead frames the dist/snake-{dark,light}.svg that Platane/snk produced
in the same card as the calendar (no token needed).
Only the standard library is used. Fonts are embedded from scripts/fonts.json (which also carries their advance
widths, for measuring text), the panel illustration from scripts/stats.jpg (see prep_images.py).
Only public repositories are counted, so a local run with a personal token matches the Actions run.
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

from maple import LEAF_COLORS, leaf_def
from paper import punch
from sunlight import light_rays

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "dist")
LOGIN = os.environ.get("GH_LOGIN", "Shxiao101")
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")

FONTS = json.load(open(os.path.join(HERE, "fonts.json"), encoding="utf-8"))
STATS_IMG = base64.b64encode(open(os.path.join(HERE, "stats.jpg"), "rb").read()).decode()

QUERY = """
query($login: String!) {
  user(login: $login) {
    followers { totalCount }
    pullRequests { totalCount }
    issues { totalCount }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, orderBy: {field: STARGAZERS, direction: DESC}) {
      totalCount
      nodes {
        name description pushedAt stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
    contributionsCollection {
      totalCommitContributions
      restrictedContributionsCount
      totalRepositoriesWithContributedCommits
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount contributionLevel } }
      }
    }
  }
}
"""
# github's own 5-step colouring (the same one Platane/snk reads), so the calendar and the snake agree
LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}


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


def streaks(days, today):
    """All-time total plus current and longest streak as (length, first day, last day).
    Today still counts as open: a streak that ran through yesterday is kept."""
    days = [(dt.date.fromisoformat(k), c) for k, c in days if dt.date.fromisoformat(k) <= today]
    longest, run, start = (0, None, None), 0, None
    for day, c in days:
        if c > 0:
            start = day if run == 0 else start
            run += 1
            if run > longest[0]:
                longest = (run, start, day)
        else:
            run = 0
    i = len(days) - 1
    if i >= 0 and days[i][1] == 0:
        i -= 1
    end, n = (days[i][0] if i >= 0 else None), 0
    while i >= 0 and days[i][1] > 0:
        n += 1
        i -= 1
    current = (n, days[i + 1][0], end) if n else (0, None, None)
    first = next((day for day, c in days if c > 0), None)
    return {"total": sum(c for _, c in days), "current": current, "longest": longest, "first": first}


PR_QUERY = """
query($login: String!, $after: String) {
  user(login: $login) {
    pullRequests(states: MERGED, first: 100, after: $after, orderBy: {field: CREATED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes { repository { name isPrivate stargazerCount owner { login } primaryLanguage { name } } }
    }
  }
}
"""


def merged_upstream():
    """Other people's public repositories that merged my pull requests: most merged first, then most starred."""
    groups, after = {}, None
    for _ in range(10):
        page = gql(PR_QUERY, {"login": LOGIN, "after": after})["user"]["pullRequests"]
        for n in page["nodes"]:
            r = n["repository"]
            if not r or r["isPrivate"] or r["owner"]["login"].lower() == LOGIN.lower():
                continue
            g = groups.setdefault((r["owner"]["login"], r["name"]), {
                "owner": r["owner"]["login"], "name": r["name"], "stars": r["stargazerCount"],
                "lang": (r["primaryLanguage"] or {}).get("name"), "count": 0})
            g["count"] += 1
        if not page["pageInfo"]["hasNextPage"]:
            break
        after = page["pageInfo"]["endCursor"]
    return sorted(groups.values(), key=lambda g: (-g["count"], -g["stars"], g["name"].lower()))


SKIP_LANGS = {"XSLT", "Makefile", "DTrace", "HTML", "Shell", "Batchfile", "CMake"}


def collect():
    u = gql(QUERY, {"login": LOGIN})["user"]
    repos = u["repositories"]["nodes"]
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
    cc = u["contributionsCollection"]
    weeks = [[(d["date"], d["contributionCount"], LEVELS[d["contributionLevel"]]) for d in w["contributionDays"]]
             for w in cc["contributionCalendar"]["weeks"]]
    days = [d for w in weeks for d in w]
    today = dt.date.fromisoformat(days[-1][0])   # the calendar ends on github's "today"
    return {
        "today": today,
        "streak": streaks(all_days(), today),
        "stars": sum(r["stargazerCount"] for r in repos),
        "repos": u["repositories"]["totalCount"],
        "commits": cc["totalCommitContributions"] + cc["restrictedContributionsCount"],
        "prs": u["pullRequests"]["totalCount"],
        "issues": u["issues"]["totalCount"],
        "contributed_to": cc["totalRepositoriesWithContributedCommits"],
        "followers": u["followers"]["totalCount"],
        "total": cc["contributionCalendar"]["totalContributions"],
        "active_days": sum(1 for _, c, _ in days if c > 0),
        "days_count": len(days),
        "weeks": weeks,
        "langs": top,
        "own": [{"name": r["name"], "pushed": dt.date.fromisoformat(r["pushedAt"][:10]),
                 "desc": " ".join((r["description"] or "").split()),
                 "langs": [e["node"]["name"] for e in r["languages"]["edges"] if e["node"]["name"] not in SKIP_LANGS]}
                for r in own],
        "upstream": merged_upstream(),
    }


PAL = {
    "dark": dict(
        bg0="#1b180e", bg1="#121210", border="#3a3418",
        title="#fbf6e0", label="#c2b788", value="#fbf6e0", muted="#9a9068",
        accent="#e4cf5a", accent2="#a0a741", track="#2c2814",
        levels=["#2a221a", "#5c2a16", "#9c3a18", "#e0552a", "#ff9660"],   # maple: ember to vermilion to glow
        langs=["#f2e173", "#d9b84a", "#a0a741", "#6fb8a8", "#f5d49f", "#b38f2e"],
        grad0="#ffffff", grad1="#e4cf5a",
        pbg0="#1b180e", pbg1="#121210", pbg2="#0d1413", frame="#e8d98a", frameO=".20", grainO=".045",
        blobA="#c9a227", blobAo=".26", blobB="#2f6b62", blobBo=".34", blobC="#8b6fb0", blobCo=".22",
        spark="#fff2b0", toneR="0 .5 .9", toneG="0 .46 .82", toneB="0 .4 .7",
        # bookshelf and contents page
        wood="#6b4a2a", wood0="#553820", wood1="#3a2613", woodLine="#1e1208", wallShade="#000", wallShadeO=".55",
        bookShade="#000", bookShadeO=".55", clothDim=".2", foil="#ecd27a", foilDark="#2a1d0a", paperLabel="#e9dcb8",
        vase0="#7aa593", vase1="#3c5c50", metal0="#8a826c", metal1="#4a453a", stem="#8a5a32",
        ribbon0="#e0552a", ribbon1="#9c3a18", ribbonShadeO=".35", gutter="#000", gutterO=".42",
        nextPage="#221e13", flap0="#0e0d08", flap1="#5c5238", flap2="#39321f", flap3="#282316", curlShadeO=".5"),
    "light": dict(
        bg0="#fffdf3", bg1="#f8f2d8", border="#e6dcae",
        title="#3b340c", label="#6f6434", value="#3b340c", muted="#8f8454",
        accent="#a8841a", accent2="#6f7a1a", track="#eee5bf",
        levels=["#f1e7d3", "#f8c89a", "#f08a4b", "#d9481c", "#a82a10"],   # maple: pale amber to vermilion to deep red
        langs=["#a8841a", "#d4b64a", "#6f7a1a", "#3f8f7f", "#d49a5a", "#5e4c0c"],
        grad0="#3b340c", grad1="#a8841a",
        pbg0="#faf4d9", pbg1="#fffdf3", pbg2="#f0f2df", frame="#8a7a1a", frameO=".18", grainO=".03",
        blobA="#f2e173", blobAo=".50", blobB="#d8e3a4", blobBo=".55", blobC="#e6dcf5", blobCo=".70",
        spark="#b8921c", toneR="0 1", toneG="0 1", toneB="0 1",
        wood="#dcb682", wood0="#c0915a", wood1="#9a6a38", woodLine="#6b4520", wallShade="#7a5a2a", wallShadeO=".22",
        bookShade="#5a4520", bookShadeO=".22", clothDim="0", foil="#f3d98a", foilDark="#3a2a10", paperLabel="#fbf5e2",
        vase0="#b3d0c1", vase1="#6f9483", metal0="#c2b9a2", metal1="#7d7462", stem="#7a5230",
        ribbon0="#d9481c", ribbon1="#a82a10", ribbonShadeO=".16", gutter="#6b5a2a", gutterO=".16",
        nextPage="#efe4c3", flap0="#cdbb86", flap1="#fffbef", flap2="#f3e8cb", flap3="#e4d5aa", curlShadeO=".16"),
}


def fontface(key):
    f = FONTS[key]
    return ("@font-face{font-family:'%s';font-style:%s;font-weight:%s;"
            "src:url(data:font/woff2;base64,%s) format('woff2');}\n"
            % (f["family"], f["style"], f["weight"], f["b64"]))


CSS = (fontface("outfit") + fontface("jbmono") +
       ".t{font-family:'Outfit',sans-serif;font-weight:800}"
       ".m{font-family:'JetBrains Mono',monospace;font-weight:500}"
       "@keyframes pop{from{opacity:0;transform:scale(.55)}to{opacity:1;transform:scale(1)}}"
       ".c{transform-box:fill-box;transform-origin:center;animation:pop .5s cubic-bezier(.2,.8,.2,1) both}"
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


def short(n):
    return f"{n/1000:.1f}k" if n >= 1000 else str(n)


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


EASE = ".45 0 .55 1"


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


def smooth_fade_in(n=10):
    """Smoothstep 0 -> 1 opacity stops; a linear ramp leaves a visible kink where the picture starts."""
    return "".join(f'<stop offset="{i/n:.2f}" stop-color="#fff" stop-opacity="{3*(i/n)**2 - 2*(i/n)**3:.3f}"/>'
                   for i in range(n + 1))


def star_path(s):
    k = s * 0.22
    return f"M0,{-s:.1f} L{k:.1f},{-k:.1f} L{s:.1f},0 L{k:.1f},{k:.1f} L0,{s:.1f} L{-k:.1f},{k:.1f} L{-s:.1f},0 L{-k:.1f},{-k:.1f} Z"


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
    body.append('<line x1="56" y1="262" x2="636" y2="262" stroke="url(#pline)" stroke-width="1.2"/>')
    rows = [("star", "stars", d["stars"]), ("commit", "commits", d["commits"]),
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
<linearGradient id="pline" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{p['accent']}" stop-opacity=".7"/><stop offset="1" stop-color="{p['accent']}" stop-opacity="0"/></linearGradient>
<linearGradient id="pfade" gradientUnits="userSpaceOnUse" x1="{ix}" y1="0" x2="{ix+230}" y2="0">{smooth_fade_in()}</linearGradient>
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


def calendar_card(theme, d):
    p = PAL[theme]
    W, H = 1200, 240
    x0, y0, cell, gap = 48, 78, 16, 4
    step = cell + gap
    weeks = d["weeks"]

    cells, labels = [], []
    last_month, last_label_x = None, -999
    for wi, week in enumerate(weeks):
        x = x0 + wi * step
        first = dt.date.fromisoformat(week[0][0])
        if first.month != last_month:
            if x - last_label_x >= 3 * step and wi < len(weeks) - 2:
                labels.append(f'<text x="{x}" y="{y0-12}" class="m" font-size="11" fill="{p["muted"]}">{first.strftime("%b").lower()}</text>')
                last_label_x = x
            last_month = first.month
        for date, count, lv in week:
            di = dt.date.fromisoformat(date).weekday()  # mon=0 … sun=6
            di = (di + 1) % 7  # sun=0 … sat=6, like github
            y = y0 + di * step
            cells.append(f'<rect class="c" x="{x}" y="{y}" width="{cell}" height="{cell}" rx="3.5" fill="{p["levels"][lv]}" style="animation-delay:{wi*0.018:.3f}s"><title>{date}: {count}</title></rect>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="contribution calendar of {LOGIN}">'
            + card_frame(p, W, H, "C")
            + f'<g transform="translate(58 34)" fill="{p["accent"]}">{ICON["star"]}</g>'
            + f'<text x="76" y="40" class="t" font-size="19" fill="url(#tgC)">contributions</text>'
            + f'<text x="{W-x0}" y="40" class="m" font-size="12" text-anchor="end" fill="{p["label"]}">{fmt(d["total"])} contributions · {d["active_days"]} active days · last 12 months</text>'
            + "".join(labels) + "".join(cells) + "</svg>")


SHELF_Y = 258          # top of the shelf board, where the books stand


def spine_trim(style, x, y, w, h, foil, p, ornament):
    """Gilt and label work on a spine; every volume of one language shares a style, like a set."""
    def rule(yy, hh=1.4, o=.85):
        return f'<rect x="{x + 2.5:.1f}" y="{yy:.1f}" width="{w - 5:.1f}" height="{hh}" fill="{foil}" opacity="{o}"/>'
    foot = y + h
    # a small gilt lozenge mid-spine where there's no title
    lozenge = (f'<rect x="-2.6" y="-2.6" width="5.2" height="5.2" transform="translate({x + w / 2:.1f} {y + h * .45:.1f}) rotate(45)" '
               f'fill="{foil}" opacity=".7"/>' if ornament else "")
    if style == 0:        # double gilt rules at head and foot
        return rule(y + 11) + rule(y + 15.5) + rule(foot - 19) + rule(foot - 14.5) + lozenge
    if style == 1:        # dark leather bands edged in gilt
        return lozenge + "".join(f'<rect x="{x:.1f}" y="{yy:.1f}" width="{w:.1f}" height="13" fill="#000" opacity=".24"/>'
                                 + rule(yy - 1.6, 1.2, .8) + rule(yy + 13.4, 1.2, .8) for yy in (y + 9, foot - 24))
    # a library label near the foot, one broad gilt rule at the head
    return (rule(y + 12, 2.2) + f'<rect x="{x + 4:.1f}" y="{foot - 37:.1f}" width="{w - 8:.1f}" height="17" rx="1.5" fill="{p["paperLabel"]}" opacity=".92"/>'
            f'<rect x="{x + 7:.1f}" y="{foot - 29.5:.1f}" width="{w - 14:.1f}" height="1.2" fill="#5a4a2a" opacity=".45"/>')


def vase(p, cx, base):
    """A celadon bud vase with a sprig of maple that sways a little, and now and then drops a leaf on the shelf."""
    rnd = random.Random(3)
    mouth = base - 54
    stems = ["M0,4 C-3,-22 -14,-44 -30,-66", "M1,4 C4,-26 10,-52 20,-86", "M0,4 C2,-14 0,-28 8,-44"]
    # (x, y, scale, angle): at the stem tips and along the stems, relative to the mouth
    spots = [(-30, -66, 1.25, -35), (-13, -37, .9, -62), (20, -86, 1.3, 14), (9, -52, .95, 58), (8, -44, 1.0, 30)]
    leaves = []
    for x, y, s, a in spots:
        c = rnd.choice(LEAF_COLORS)
        dur, beg = rnd.uniform(3.5, 5.5), -rnd.uniform(0, 5)
        leaves.append(
            f'<g transform="translate({x} {y}) rotate({a})"><g>'
            f'<animateTransform attributeName="transform" type="rotate" values="-7;7;-7" keyTimes="0;.5;1" calcMode="spline" '
            f'keySplines="{EASE};{EASE}" dur="{dur:.1f}s" begin="{beg:.1f}s" repeatCount="indefinite"/>'
            f'<use href="#vleaf" transform="scale({s})" fill="{c}" stroke="{c}" stroke-width=".8" stroke-linejoin="round"/></g></g>')
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
            f'<use href="#vleaf" transform="scale(1.1)" fill="{c}" stroke="{c}" stroke-width=".8"/></g></g></g></g>')
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
        if v["first"] and w >= 18 and text_width("outfit", v["name"], 11, .6) <= h - 70:
            # spine titles read top to bottom; rotated, the glyphs sit to the right of the baseline
            title = (f'<text transform="translate({x + w / 2 - 4:.1f} {y + 32:.1f}) rotate(90)" class="t" font-size="11" '
                     f'letter-spacing=".6" fill="{foil}">{esc(v["name"])}</text>')
        body = (f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="2" fill="{v["c"]}"/>'
                + spine_trim(v["si"] % 3, x, y, w, h, foil, p, not title) + title
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
    bx = X1 + 7
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


def toc_card(theme, d):
    """The repositories as a book's contents: an open spread with my own repositories on the left page and, on the
    right, the marginalia - other people's projects that merged my pull requests.  A ribbon lies in the gutter."""
    p = PAL[theme]
    W = 1200
    today = d["today"]

    def when(day):
        m = day.strftime("%b").lower()
        return f"{m} {day.day}" if day.year == today.year else f"{m} {day.year}"

    left = []
    for r in d["own"][:4]:
        about = [r["langs"][0], r["desc"]] if r["desc"] and r["langs"] else [r["desc"] or ", ".join(r["langs"][:3])]
        left.append((r["name"], when(r["pushed"]), "  ·  ".join(a for a in about if a)))
    right, per_owner = [], {}
    for g in d["upstream"]:   # two repositories per owner at most, so one busy organisation doesn't fill the page
        if len(right) < 4 and per_owner.get(g["owner"], 0) < 2:
            per_owner[g["owner"]] = per_owner.get(g["owner"], 0) + 1
            right.append((g["name"], str(g["count"]),
                          "  ·  ".join([g["owner"], f"{short(g['stars'])} stars"] + ([g["lang"]] if g["lang"] else []))))
    Y0, PITCH = 168, 58
    rows = max(len(left), len(right), 1)
    H = Y0 + (rows - 1) * PITCH + 90
    pages = [(96, 552, "Contents", "part i  ·  my repositories", "last pushed", left, 0),
             (648, 1104, "Marginalia", "part ii  ·  merged upstream", "merged prs", right, len(left))]
    body, n, latest = [], 0, None
    for pi, (x0, x1, title, part, col, entries, first) in enumerate(pages):
        body.append(f'<text x="{x0}" y="84" class="h" font-size="46" fill="url(#tgT)">{title}</text>'
                    f'<text x="{x0}" y="118" class="m" font-size="12" letter-spacing="2" fill="{p["accent"]}">{part}</text>'
                    f'<text x="{x1}" y="118" class="m" font-size="11" text-anchor="end" fill="{p["muted"]}">{col}</text>'
                    f'<rect x="{x0}" y="131" width="{x1 - x0}" height="1.2" fill="url(#rule)"/>'
                    f'<text x="{(x0 + x1) / 2}" y="{H - 26}" text-anchor="middle" class="h" font-size="20" fill="{p["muted"]}">~ {pi + 1} ~</text>')
        if not entries:
            body.append(f'<text x="{x0 + 36}" y="{Y0}" class="h" font-size="24" fill="{p["muted"]}">blank pages, for now</text>')
        for j, (name, value, sub) in enumerate(entries):
            y = Y0 + j * PITCH
            entry, nx, nw = toc_entry(p, x0, x1, y, first + j, name, value, sub, .3 + n * .18)
            body.append(entry)
            n += 1
            if pi == 0 and j == 0:
                latest = (nx, nw, y)
    underline = ""
    if latest:   # a red-pencil underline under the latest chapter, once the pages are written
        nx, nw, y = latest
        underline = (f'<path d="M{nx - 3:.1f},{y + 7} C{nx + nw * .3:.1f},{y + 3} {nx + nw * .65:.1f},{y + 10} {nx + nw + 5:.1f},{y + 4.5}" '
                     f'fill="none" stroke="{p["ribbon0"]}" stroke-width="2.4" stroke-linecap="round" opacity=".85" pathLength="1" stroke-dasharray="1 1">'
                     f'<set attributeName="stroke-dashoffset" to="1" begin="0s" fill="freeze"/>'
                     f'<animate attributeName="stroke-dashoffset" from="1" to="0" begin="{.3 + n * .18 + .5:.2f}s" dur=".6s" fill="freeze"/></path>')
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
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="contents: repositories of {LOGIN}">'
            + f'<defs>{curl_defs}</defs>' + next_page + '<g clip-path="url(#curl)">'
            + card_frame(p, W, H, "T")
            + f'<defs><style><![CDATA[{css}]]></style>'
            f'<linearGradient id="gut" x1="0" y1="0" x2="1" y2="0">{gut}</linearGradient>'
            f'<linearGradient id="rule" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{p["accent"]}" stop-opacity=".7"/><stop offset="1" stop-color="{p["accent"]}" stop-opacity="0"/></linearGradient>'
            f'<linearGradient id="rib" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{p["ribbon1"]}"/><stop offset=".35" stop-color="{p["ribbon0"]}"/>'
            f'<stop offset="1" stop-color="{p["ribbon1"]}"/></linearGradient>'
            f'<filter id="rblur" x="-50%" y="-10%" width="200%" height="120%"><feGaussianBlur stdDeviation="2.5"/></filter></defs>'
            + f'<rect x="540" y="1.5" width="120" height="{H - 3}" fill="url(#gut)"/>'
            + f'<line x1="600" y1="1.5" x2="600" y2="{H - 1.5}" stroke="{p["gutter"]}" stroke-opacity="{p["gutterO"]}"/>'
            + "".join(body) + underline + ribbon + "</g>" + flap + "</svg>")


def snake_card(theme, raw):
    """Nest snk's svg in the calendar's card, scaled so its cells line up with the calendar grid above it.
    Only fonts and .t/.m go in the style block: snk's own css uses .c/.s/.u and would clash with the calendar's."""
    p = PAL[theme]
    W, H = 1200, 300
    vb = re.search(r'viewBox="([^"]+)"', raw).group(1)
    vx, vy, vw, vh = map(float, vb.split())
    inner = raw[raw.index(">", raw.index("<svg")) + 1:raw.rindex("</svg>")]
    scale = 20 / 16               # snk: 12px cells on a 16px pitch; calendar card: 16px cells on a 20px pitch
    gx, gy = 48, 78               # top-left of the calendar card's grid
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
            f'<text x="76" y="40" class="t" font-size="19" fill="url(#tgN)">snake</text>'
            f'<text x="{W-gx}" y="40" class="m" font-size="12" text-anchor="end" fill="{p["label"]}">eating the last 12 months</text>'
            f'<svg x="{gx + vx*scale:.1f}" y="{gy + vy*scale:.1f}" width="{vw*scale:.1f}" height="{vh*scale:.1f}" viewBox="{vb}">{inner}</svg>'
            f'</svg>')


def wrap_snake():
    for theme in ("dark", "light"):
        path = os.path.join(OUT, f"snake-{theme}.svg")
        raw = open(path, encoding="utf-8").read()
        if 'aria-label="contribution snake of' in raw:
            continue
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(punch(snake_card(theme, raw), theme == "dark"))
        print(f"framed {path} ({os.path.getsize(path)//1024} KB)")


def main():
    if sys.argv[1:] == ["snake"]:
        return wrap_snake()
    os.makedirs(OUT, exist_ok=True)
    d = collect()
    for theme in ("dark", "light"):
        for name, fn in (("stats", stats_panel), ("calendar", calendar_card), ("shelf", shelf_card), ("toc", toc_card)):
            path = os.path.join(OUT, f"{name}-{theme}.svg")
            svg = fn(theme, d)
            if name != "toc":   # the contents page is a book page, with a curled corner instead of binder holes
                svg = punch(svg, theme == "dark")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(svg)
            print(f"wrote {path} ({os.path.getsize(path)//1024} KB)")
    print(json.dumps({k: v for k, v in d.items() if k != "weeks"}, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
