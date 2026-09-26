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
import colorsys
import datetime as dt
import html
import json
import os
import random
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request

from common import EASE, FONTS, esc, fontface, smooth_fade, star_path, write_svg
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

with open(os.path.join(HERE, "stats.jpg"), "rb") as fh:
    STATS_IMG = base64.b64encode(fh.read()).decode()
with open(os.path.join(HERE, "works.jpg"), "rb") as fh:
    WORKS_IMG = base64.b64encode(fh.read()).decode()

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


def gql(query, variables, retries=2):
    if not TOKEN:
        sys.exit("GITHUB_TOKEN is not set")
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql", data=body,
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json",
                 "User-Agent": "profile-cards"})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                res = json.load(resp)
            if res.get("errors"):
                sys.exit(json.dumps(res["errors"], indent=2))
            return res["data"]
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            if attempt < retries and e.code in (429, 500, 502, 503, 504):
                time.sleep(1.5 * (attempt + 1))
                continue
            sys.exit(f"GitHub GraphQL HTTP {e.code}: {e.reason}\n{err_body}")
        except urllib.error.URLError as e:
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            sys.exit(f"Network error connecting to GitHub: {e.reason}")


YEARS_QUERY = "query($login: String!) { user(login: $login) { contributionsCollection { contributionYears } } }"


def all_days(chunk_size=5):
    """Every calendar day of every contribution year, as sorted (date, count) pairs."""
    years = gql(YEARS_QUERY, {"login": LOGIN})["user"]["contributionsCollection"]["contributionYears"]
    if not years:
        return []
    days = {}
    for i in range(0, len(years), chunk_size):
        chunk = years[i:i + chunk_size]
        fields = " ".join(
            f'y{y}: contributionsCollection(from: "{y}-01-01T00:00:00Z", to: "{y}-12-31T23:59:59Z") '
            "{ contributionCalendar { weeks { contributionDays { date contributionCount } } } }" for y in chunk)
        u = gql("query($login: String!) { user(login: $login) { %s } }" % fields, {"login": LOGIN})["user"]
        for y in chunk:
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
    # chapter ii: the pinned repositories
    works = [volume(r) for r in u["pinnedItems"]["nodes"] if r and not r["isPrivate"]][:WORKS_MAX]
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
    }


def volume(r):
    """A repository as one volume in the works-in-progress bookcase: its main language colours the cover's wash."""
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
        bookShade="#000", bookShadeO=".55", clothDim="0", foil="#ecd27a", foilDark="#2a1d0a",
        vase0="#7aa593", vase1="#3c5c50", metal0="#8a826c", metal1="#4a453a", stem="#8a5a32",
        ribbon0="#e0552a", ribbon1="#9c3a18", ribbonShadeO=".35", gutter="#000", gutterO=".42",
        nextPage="#221e13", flap0="#0e0d08", flap1="#5c5238", flap2="#39321f", flap3="#282316", curlShadeO=".5", blossom="#f2a2b5",
        # works-in-progress bookcase: the bunkobon jackets and the case's back panel
        glintO=".16",
        paper="#efe6cf", ink="#2b2418", inkMuted="#6d604a", coverDim=".1", back0="#2b1e13", back1="#1a120b"),
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
        glintO=".22",
        paper="#fffbf2", ink="#2b2418", inkMuted="#6d604a", coverDim="0", back0="#e6d0a8", back1="#d2b88a"),
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


def hex_to_hls(hex_str):
    r, g, b = (v / 255.0 for v in rgb(hex_str))
    return colorsys.rgb_to_hls(r, g, b)


def hls_to_hex(h, l, s):
    rgb_t = colorsys.hls_to_rgb(h, max(0.05, min(0.95, l)), max(0.1, min(1.0, s)))
    return "#" + "".join(f"{round(x * 255):02x}" for x in rgb_t)


def hue_dist(h1, h2):
    diff = abs(h1 - h2)
    return min(diff, 1.0 - diff)


def resolve_cloth_colors(langs, fallback):
    """100% faithful to GitHub official colors with zero hardcoded language names.
    Detects any languages on the shelf that share the same color family (Hue distance < 30°),
    and automatically polarizes lightness (dominant -> deep Oxford shade L~0.24, second -> bright
    Royal shade L~0.54, third -> light tint L~0.72) while strictly preserving each language's
    exact GitHub official hue angle. Non-colliding languages use 100% untouched GitHub colors."""
    raw_colors = [c or fallback[i % len(fallback)] for i, (_, _, c) in enumerate(langs)]
    n = len(langs)
    hls_list = [hex_to_hls(c) for c in raw_colors]
    out = list(raw_colors)

    visited = set()
    clusters = []
    for i in range(n):
        if i in visited:
            continue
        cluster = [i]
        visited.add(i)
        for j in range(i + 1, n):
            if j not in visited and hue_dist(hls_list[i][0], hls_list[j][0]) < 0.083:
                cluster.append(j)
                visited.add(j)
        clusters.append(cluster)

    for cluster in clusters:
        if len(cluster) == 1:
            continue
        levels = [0.24, 0.54, 0.72, 0.38, 0.62]
        for rank, idx in enumerate(cluster):
            h, l, s = hls_list[idx]
            target_l = levels[rank % len(levels)]
            target_s = min(0.85, max(0.45, s * 1.15))
            out[idx] = hls_to_hex(h, target_l, target_s)

    return {langs[i][0]: out[i] for i in range(n)}


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
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="github stats of {esc(LOGIN)}">
<defs><style><![CDATA[{CSS}]]></style>
<clipPath id="pcard"><rect width="{W}" height="{H}" rx="28" ry="28"/></clipPath>
<linearGradient id="pbg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{p['pbg0']}"/><stop offset=".55" stop-color="{p['pbg1']}"/><stop offset="1" stop-color="{p['pbg2']}"/></linearGradient>
<linearGradient id="pgrad" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{p['grad0']}"/><stop offset="1" stop-color="{p['grad1']}"/></linearGradient>
<linearGradient id="pbar" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{p['accent2']}"/><stop offset="1" stop-color="{p['accent']}"/></linearGradient>
<linearGradient id="pline" gradientUnits="userSpaceOnUse" x1="56" y1="0" x2="636" y2="0"><stop offset="0" stop-color="{p['accent']}" stop-opacity=".7"/><stop offset="1" stop-color="{p['accent']}" stop-opacity="0"/></linearGradient>
<linearGradient id="pfade" gradientUnits="userSpaceOnUse" x1="{ix}" y1="0" x2="{ix+230}" y2="0">{smooth_fade(fade_in=True)}</linearGradient>
<mask id="pmask"><rect x="{ix}" y="0" width="{IW}" height="{H}" fill="url(#pfade)"/></mask>
<filter id="pblur" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="45"/></filter>
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
ROMAN_NUMS = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
              "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX",
              "XXI", "XXII", "XXIII", "XXIV", "XXV", "XXVI", "XXVII", "XXVIII", "XXIX", "XXX",
              "XXXI", "XXXII", "XXXIII", "XXXIV", "XXXV"]


def roman(n):
    return ROMAN_NUMS[n] if 0 < n < len(ROMAN_NUMS) else str(n)


def spine_trim(style, x, y, w, foil, ornament, vol_idx=0):
    """Gilt work and raised bands on a spine, the foot a mirror image of the head; every volume of one language
    shares a style, like a set.  The front of the shelf board hides the bottom 4px of each book, so the foot is
    measured from what shows."""
    head, foot = y, SHELF_Y - 4

    def mirrored(d, hh, piece):   # `piece(top_y)` d px in from the head, and again d px in from the foot
        return piece(head + d) + piece(foot - d - hh)

    def rule(d, hh=1.4, o=.85):
        return mirrored(d, hh, lambda yy: f'<rect x="{x + 2.5:.1f}" y="{yy:.1f}" width="{w - 5:.1f}" height="{hh}" fill="{foil}" opacity="{o}"/>')

    # 4 raised bands (bamboo ribs / sewing cords) across the spine
    span = foot - head
    bands = []
    for frac in (0.22, 0.41, 0.61, 0.80):
        by = head + span * frac
        bands.append(
            f'<rect x="{x:.1f}" y="{by:.1f}" width="{w:.1f}" height="1" fill="#fff" opacity=".18"/>'
            f'<rect x="{x:.1f}" y="{by + 1:.1f}" width="{w:.1f}" height="2" fill="#000" opacity=".22"/>'
            f'<rect x="{x:.1f}" y="{by + 3:.1f}" width="{w:.1f}" height="1" fill="#000" opacity=".35"/>'
        )
    ribs = "".join(bands)

    mid_y = (head + foot) / 2
    if vol_idx > 0 and w >= 16:
        # Classical Roman volume numbering for multi-volume collection
        num_str = roman(vol_idx + 1)
        font_sz = min(9.5, max(7.0, w * 0.42))
        vol_label = (
            f'<rect x="-2" y="-2" width="4" height="4" transform="translate({x + w / 2:.1f} {mid_y - font_sz - 4:.1f}) rotate(45)" fill="{foil}" opacity=".6"/>'
            f'<text x="{x + w / 2:.1f}" y="{mid_y + font_sz * 0.35:.1f}" text-anchor="middle" class="m" font-size="{font_sz:.1f}" '
            f'font-weight="700" letter-spacing="0.5" fill="{foil}" opacity=".9">{num_str}</text>'
            f'<rect x="-2" y="-2" width="4" height="4" transform="translate({x + w / 2:.1f} {mid_y + font_sz + 4:.1f}) rotate(45)" fill="{foil}" opacity=".6"/>'
        )
    elif ornament:
        vol_label = (f'<rect x="-2.6" y="-2.6" width="5.2" height="5.2" transform="translate({x + w / 2:.1f} {mid_y:.1f}) rotate(45)" '
                     f'fill="{foil}" opacity=".7"/>')
    else:
        vol_label = ""

    if style == 0:        # double gilt rules
        trim = rule(11) + rule(15.5) + vol_label
    elif style == 1:      # dark leather bands edged in gilt
        band = mirrored(9, 13, lambda yy: f'<rect x="{x:.1f}" y="{yy:.1f}" width="{w:.1f}" height="13" fill="#000" opacity=".24"/>')
        trim = band + rule(7.4, 1.2, .8) + rule(22.4, 1.2, .8) + vol_label
    else:
        trim = rule(12, 2.4) + vol_label   # one broad gilt rule
    return ribs + trim

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
    body = (
        # Wooden footed stand ring
        f'<ellipse cx="{cx}" cy="{base + 1}" rx="14" ry="3.5" fill="{p["wood1"]}"/>'
        f'<ellipse cx="{cx}" cy="{base}" rx="13" ry="3" fill="url(#wood)"/>'
        # Drop shadow onto shelf
        f'<ellipse cx="{cx}" cy="{base + 2}" rx="15" ry="3.8" fill="#000" opacity="{p["wallShadeO"]}" filter="url(#bshade)"/>'
        # Vase porcelain body
        f'<path d="M{cx - 5},{mouth} Q{cx - 6},{mouth + 8} {cx - 15},{mouth + 28} '
        f'Q{cx - 20},{mouth + 44} {cx - 16},{base - 4} Q{cx - 15},{base} {cx},{base} '
        f'Q{cx + 15},{base} {cx + 16},{base - 4} Q{cx + 20},{mouth + 44} {cx + 15},{mouth + 28} '
        f'Q{cx + 6},{mouth + 8} {cx + 5},{mouth} Z" fill="url(#vaseG)"/>'
        # Delicate celadon crackle glaze veins (冰裂开片纹)
        f'<path d="M{cx - 6},{mouth + 20} Q{cx - 2},{mouth + 28} {cx + 2},{mouth + 26} T{cx + 8},{mouth + 38} '
        f'M{cx - 12},{mouth + 32} Q{cx - 6},{mouth + 42} {cx - 1},{mouth + 38} T{cx + 6},{mouth + 46}" '
        f'fill="none" stroke="{p["stem"]}" stroke-opacity=".18" stroke-width=".7" stroke-linecap="round"/>'
        # Specular glaze highlight (瓷器玉质双层高光弧)
        f'<path d="M{cx - 8},{mouth + 14} Q{cx - 15},{mouth + 28} {cx - 12},{base - 8}" '
        f'fill="none" stroke="#fff" stroke-opacity=".45" stroke-width="2.6" stroke-linecap="round"/>'
        f'<path d="M{cx - 8},{mouth + 14} Q{cx - 15},{mouth + 28} {cx - 12},{base - 8}" '
        f'fill="none" stroke="#fff" stroke-opacity=".80" stroke-width="1.0" stroke-linecap="round"/>'
        # Porcelain lip rim (卷沿)
        f'<ellipse cx="{cx}" cy="{mouth}" rx="5.8" ry="2.4" fill="url(#vaseG)"/>'
        f'<ellipse cx="{cx}" cy="{mouth}" rx="4.8" ry="1.8" fill="{p["vase1"]}"/>'
        f'<ellipse cx="{cx}" cy="{mouth - 0.4}" rx="5.2" ry="1.2" fill="none" stroke="#fff" stroke-opacity=".5" stroke-width=".8"/>'
    )
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
    dark = theme == "dark"
    rnd = random.Random(7)

    langs = d["langs"]
    N, X0, X1 = 34, 60, 1046
    if len(langs) > N:
        langs = langs[:N]
    raw = [s * N for _, s, _ in langs]
    counts = [max(1, int(r)) for r in raw]
    while langs and sum(counts) < N:          # largest remainder
        i = max(range(len(raw)), key=lambda i: raw[i] - counts[i])
        counts[i] += 1
    while sum(counts) > N:
        candidates = [i for i in range(len(raw)) if counts[i] > 1]
        if not candidates:
            break
        i = max(candidates, key=lambda i: counts[i] - raw[i])
    cloth_map = resolve_cloth_colors(langs, p["langs"])
    vols = []
    for si, ((name, _, color), n) in enumerate(zip(langs, counts)):
        base_color = cloth_map.get(name, color or p["langs"][si % len(p["langs"])])
        cloth = base_color
        if p["clothDim"] != "0":
            cloth = mix(cloth, "#000", float(p["clothDim"]))
        bw, bh = rnd.uniform(24, 31), rnd.uniform(146, 172)
        for k in range(n):   # a set, but no two volumes quite alike: worn, faded, a little taller or thinner
            vols.append({"si": si, "name": name, "first": k == 0, "idx": k, "w": bw * rnd.uniform(.84, 1.16),
                         "h": min(184, bh + rnd.uniform(-10, 10)), "cloth": cloth,
                         "c": mix(cloth, rnd.choice(("#000", "#fff")), rnd.uniform(0, .11))})
    gap = 1.2
    k = (X1 - X0 - gap * (len(vols) - 1)) / max(sum(v["w"] for v in vols), 1)
    last_idx = len(vols) - 1
    candidates = [idx for idx in range(len(vols)) if idx != last_idx]
    num_pulled = min(5, len(candidates))
    pulled = set(rnd.sample(candidates, num_pulled)) if candidates else set()
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
                + spine_trim(v["si"] % 3, x, y, w, foil, not title, vol_idx=v["idx"]) + title
                + f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="2" fill="url(#spine)"/>')
        
        # Organic tilt on the last volume, naturally resting against the brass bookend
        is_leaning = (i == last_idx and len(vols) >= 4)
        tilt_transform = f' transform="rotate(5 {x + w:.1f} {SHELF_Y})"' if is_leaning else ""

        if i in pulled and not is_leaning:   # lifted book with a crimson silk bookmark ribbon
            dur = rnd.uniform(6.5, 9.0)
            beg = -rnd.uniform(0, dur)
            ribbon_dangle = (f'<path d="M{x + w / 2 - 0.8:.1f},{y + h:.1f} Q{x + w / 2 + 2.5:.1f},{y + h + 6:.1f} {x + w / 2 - 1.5:.1f},{y + h + 12:.1f}" '
                             f'fill="none" stroke="{p["ribbon0"]}" stroke-width="1.8" stroke-linecap="round"/>')
            body = (f'<g><animateTransform attributeName="transform" type="translate" values="0 0;0 -18;0 -18;0 0;0 0" '
                    f'keyTimes="0;.22;.52;.70;1" calcMode="spline" keySplines="{EASE};0 0 1 1;{EASE};0 0 1 1" '
                    f'dur="{dur:.1f}s" begin="{beg:.1f}s" repeatCount="indefinite"/>{body}{ribbon_dangle}</g>')
        elif is_leaning:
            body = f'<g{tilt_transform}>{body}</g>'

        books.append(f'<g><title>{esc(v["name"])}</title>{body}</g>')
        if i in pulled and not is_leaning:
            shadows.append(f'<g><animate attributeName="opacity" values="1;.3;1" dur="{dur:.1f}s" begin="{beg:.1f}s" repeatCount="indefinite"/>'
                           f'<rect x="{x + 3:.1f}" y="{y + 3:.1f}" width="{w:.1f}" height="{h - 3:.1f}" rx="2"/></g>')
        elif is_leaning:
            shadows.append(f'<rect x="{x + 3:.1f}" y="{y + 3:.1f}" width="{w:.1f}" height="{h - 3:.1f}" rx="2"{tilt_transform}/>')
        else:
            shadows.append(f'<rect x="{x + 3:.1f}" y="{y + 3:.1f}" width="{w:.1f}" height="{h - 3:.1f}" rx="2"/>')
        x += w + gap
    landed = 0.5
    grain = "".join(f'<path d="M44,{SHELF_Y + yy} C{280 + 90 * j},{SHELF_Y + yy - 1.8} {680 - 70 * j},{SHELF_Y + yy + 2.2} {W - 44},{SHELF_Y + yy}" '
                    f'fill="none" stroke="{p["woodLine"]}" stroke-opacity=".26" stroke-width=".9"/>' for j, yy in enumerate((4, 7.5, 11)))
    plank = (
        # Underside wall drop shadow
        f'<rect x="44" y="{SHELF_Y + 16}" width="{W - 88}" height="32" fill="url(#wall)"/>'
        # Shelf top board (where books stand)
        f'<rect x="44" y="{SHELF_Y - 4}" width="{W - 88}" height="5" fill="{p["wood"]}"/>'
        # Front shelf board with wood gradient
        f'<rect x="44" y="{SHELF_Y}" width="{W - 88}" height="16" rx="1.5" fill="url(#wood)"/>{grain}'
        # Top chamfer highlight line (倒角高光微条)
        f'<rect x="44" y="{SHELF_Y}" width="{W - 88}" height="1.4" fill="#fff" opacity=".35"/>'
        # Bottom chamfer shadow line (下边缘阴影条)
        f'<rect x="44" y="{SHELF_Y + 15}" width="{W - 88}" height="1.4" fill="#000" opacity=".35"/>'
        # Left and right beveled brass corner brackets (黄铜边角包角)
        f'<path d="M44,{SHELF_Y - 2} L52,{SHELF_Y - 2} L44,{SHELF_Y + 6} Z" fill="url(#metal)" opacity=".7"/>'
        f'<path d="M{W - 44},{SHELF_Y - 2} L{W - 52},{SHELF_Y - 2} L{W - 44},{SHELF_Y + 6} Z" fill="url(#metal)" opacity=".7"/>'
    )
    
    # Ornate antique brass scroll bookend
    bx = X1 + 10
    foil = p["foil"]
    bookend = (
        f'<path d="M{bx - 6},{SHELF_Y} L{bx + 22},{SHELF_Y} L{bx + 19},{SHELF_Y - 6} L{bx - 4},{SHELF_Y - 6} Z" fill="url(#metal)"/>'
        f'<rect x="{bx - 4}" y="{SHELF_Y - 6}" width="23" height="1.2" fill="#fff" opacity=".3"/>'
        f'<path d="M{bx - 2},{SHELF_Y - 6} '
        f'C{bx + 1},{SHELF_Y - 28} {bx + 9},{SHELF_Y - 46} {bx + 16},{SHELF_Y - 58} '
        f'C{bx + 12},{SHELF_Y - 66} {bx + 3},{SHELF_Y - 74} {bx - 3},{SHELF_Y - 78} '
        f'L{bx - 3},{SHELF_Y - 6} Z" fill="url(#metal)"/>'
        f'<path d="M{bx + 16},{SHELF_Y - 58} C{bx + 12},{SHELF_Y - 66} {bx + 3},{SHELF_Y - 74} {bx - 3},{SHELF_Y - 78}" '
        f'fill="none" stroke="#fff" stroke-width="1.2" opacity=".35"/>'
        f'<path d="M{bx + 1},{SHELF_Y - 14} C{bx + 5},{SHELF_Y - 32} {bx + 8},{SHELF_Y - 46} {bx + 5},{SHELF_Y - 58} '
        f'C{bx + 2},{SHELF_Y - 66} {bx - 1},{SHELF_Y - 68} {bx},{SHELF_Y - 72}" '
        f'fill="none" stroke="{foil}" stroke-width="1.2" opacity=".6" stroke-linecap="round"/>'
        f'<circle cx="{bx - 2}" cy="{SHELF_Y - 81}" r="3" fill="url(#metal)"/>'
        f'<circle cx="{bx - 2.8}" cy="{SHELF_Y - 81.8}" r="1" fill="#fff" opacity=".4"/>'
    )
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
    # Sunlight and ambient light
    sun_defs, sun = light_rays("sunShelf", 30, W - 60, H, dark, from_left=True, seed=11, count=4)
    glow_color = "#e4cf5a" if dark else "#f2e173"
    glow_op = ".10" if dark else ".22"
    ambient = f'<ellipse cx="520" cy="160" rx="340" ry="110" fill="{glow_color}" opacity="{glow_op}" filter="url(#shelfGlow)"/>'

    # Contact shadow at the base of the books
    contact_shadow = (
        f'<rect x="52" y="{SHELF_Y - 14}" width="{X1 - 40}" height="14" fill="#000" opacity="{".38" if dark else ".12"}" filter="url(#bshade)"/>'
        f'<rect x="50" y="{SHELF_Y - 2}" width="{X1 - 38}" height="3" rx="1.5" fill="#000" opacity="{".60" if dark else ".25"}"/>'
    )
    css = "@keyframes late{from{opacity:0}to{opacity:1}}.late{animation:late .8s ease both}"
    note = f"{len(langs)} languages · {d['repos']} public repos · by size of code"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="languages of {esc(LOGIN)} as a bookshelf">'
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
           f'<filter id="bshade" x="-50%" y="-10%" width="200%" height="120%"><feGaussianBlur stdDeviation="3"/></filter>'
           f'<filter id="shelfGlow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="45"/></filter>{sun_defs}</defs>'
           + ambient
           + f'<g transform="translate(58 34)" fill="{p["accent"]}">{ICON["star"]}</g>'
           + f'<text x="76" y="40" class="t" font-size="19" fill="url(#tgS)">bookshelf</text>'
           + f'<text x="{W - 48}" y="40" class="m" font-size="12" text-anchor="end" fill="{p["label"]}">{note}</text>'
           + f'<g class="late" style="animation-delay:{landed:.2f}s"><g fill="{p["bookShade"]}" opacity="{p["bookShadeO"]}" filter="url(#bshade)">{"".join(shadows)}</g></g>'
           + contact_shadow
           + "".join(books) + sun + flowers + bookend + plank + falling + "".join(legend) + "</svg>")


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


WORKS_MAX = 6              # github pins six at most: three to a shelf, on one shelf or two
COVER_W, COVER_H = 196, 278    # A6, a bunkobon
FRESH_DAYS = 30            # pushed this recently, a hand-written "new chapter" note is taped to the jacket
# the bookcase is seen square on from in front of its middle: its back panel is the opening shrunk this much toward
# that eye, so inside each shelf the walls, and the shelf's top or the underside of the one above, show in perspective
DEPTH = .93
# obi colours, taken in turn as on a bookshop's new-releases shelf: (band, print, the figure that shouts)
OBIS = [("#f4d31f", "#1d1a14", "#c8281e"), ("#1f1d1b", "#f7f1e3", "#f4d31f"),
        ("#c8281e", "#fff8ea", "#ffe14a"), ("#f8f5ec", "#1d1a14", "#c8281e")]
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


WIDE = "[\u2e80-\u9fff\uac00-\ud7af\uf900-\ufaff\ufe30-\ufe4f\uff00-\uffef]"   # CJK, hangul, full-width forms


def wrap_blurb(text, size, max_w):
    """Like wrap(), but CJK text (which has no spaces) may break between any two characters, and so may a word too
    long for a line of its own."""
    lines, cur = [], ""
    toks = []
    for tok in re.findall(WIDE + r"|[^\s" + WIDE[1:-1] + r"]+|\s+", text):
        while not tok.isspace() and len(tok) > 1 and text_width("jbmono", tok, size) > max_w:
            k = max(1, next(k for k in range(len(tok), 0, -1) if text_width("jbmono", tok[:k], size) <= max_w))
            toks.append(tok[:k])
            tok = tok[k:]
        toks.append(tok)
    for tok in toks:
        if cur and not tok.isspace() and text_width("jbmono", cur + tok, size) > max_w:
            lines.append(cur.rstrip())
            cur = ""
        if cur or not tok.isspace():
            cur += " " if tok.isspace() else tok
    return lines + [cur.rstrip()] if cur.strip() else lines


def wash(p, v, base, y0, y1):
    """The cover art between y0 and y1: a watercolour wash in the language's colour, laid on a diagonal from the
    lower left to the upper right with a few splatters, and cherry petals drifting down across it.  Seeded by the
    repository's name, so each volume keeps its picture from day to day."""
    cw = COVER_W
    rnd = random.Random(v["name"])
    blobs = []
    for k in range(6):
        t = k / 5
        c = mix(base, rnd.choice(("#fff", "#000", p["paper"])), rnd.uniform(0, .45))
        if k == 3:
            c = mix(base, p["blossom"], .55)   # one wash of a second colour, as a painter would
        blobs.append(f'<ellipse cx="{20 + t * (cw - 40) + rnd.uniform(-18, 18):.0f}" cy="{y1 - 16 - t * (y1 - y0 - 30) + rnd.uniform(-12, 12):.0f}" '
                     f'rx="{rnd.uniform(38, 70):.0f}" ry="{rnd.uniform(26, 44):.0f}" fill="{c}" opacity="{rnd.uniform(.45, .8):.2f}"/>')
    dots = "".join(f'<circle cx="{rnd.uniform(8, cw - 8):.0f}" cy="{rnd.uniform(y0, y1 - 4):.0f}" r="{rnd.uniform(.6, 2.2):.1f}"/>'
                   for _ in range(12))
    petals = []
    for k in range(2):
        x0, dur, beg = rnd.uniform(30, cw - 60), rnd.uniform(11, 16), -rnd.uniform(0, 14)
        petals.append(f'<g><animateTransform attributeName="transform" type="translate" values="{x0:.0f} {y0 - 30:.0f};{x0 + 40:.0f} {(y0 + y1) / 2:.0f};{x0 + 10:.0f} {y1 + 10}" '
                      f'dur="{dur:.1f}s" begin="{beg:.1f}s" repeatCount="indefinite"/>'
                      f'<path d="{BLOSSOM_PETAL}" transform="scale(1.5)" fill="{p["blossom"]}" opacity=".85">'
                      f'<animateTransform attributeName="transform" type="rotate" values="0;200;360" additive="sum" dur="{dur:.1f}s" begin="{beg:.1f}s" repeatCount="indefinite"/></path></g>')
    return (f'<g filter="url(#wash)">{"".join(blobs)}</g><g fill="{base}" opacity=".45">{dots}</g>', "".join(petals))


def poly(*pts):
    return "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + " Z"


def cover(p, i, v, today, shade=0, number=1, band=0):
    """One bunkobon standing face out, drawn at the origin.  It opens from the right, so the jacket folds round
    the spine at the right edge.  The paper jacket carries the catalogue
    number, title and author in a band across the top and a watercolour below; the obi (colour OBIS[band])
    carries the description as its copy and the stars in a round badge.  A glint crosses the jacket now and then.
    `shade` darkens the wash, so two volumes in one language aren't twins; `number` counts the author's volumes,
    for the catalogue number."""
    cw, ch = COVER_W, COVER_H
    cx = cw / 2
    ink, dim = p["ink"], float(p["coverDim"])
    base = mix(v["color"] or p["langs"][i % len(p["langs"])], "#000", shade)
    bg, oink, hot = OBIS[band % len(OBIS)]
    oy = round(ch * .66)         # top of the obi
    # the title band: catalogue number and volume, then the title and the author, centred
    size, lines = title_lines(v["name"], cw - 36, 62)
    lead = size * LEAD
    ty = 42 + size * CAP
    last = ty + (len(lines) - 1) * lead
    top = last + 34              # the author's line; below it the picture begins
    art, petals = wash(p, v, base, top - 14, oy)
    # plain paper over the top of the jacket, fading out below the author so the wash bleeds up into it
    fade = (f'<linearGradient id="bf{i}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{p["paper"]}" stop-opacity=".94"/>'
            f'<stop offset="{(top - 4) / (top + 26):.3f}" stop-color="{p["paper"]}" stop-opacity=".94"/>'
            f'<stop offset="1" stop-color="{p["paper"]}" stop-opacity="0"/></linearGradient>')
    title = "".join(f'<text x="{cx}" y="{ty + j * lead:.1f}" text-anchor="middle" class="t" font-size="{size}" fill="{ink}">{esc(ln)}</text>'
                    for j, ln in enumerate(lines))
    head_row = (f'<text x="15" y="26" class="m" font-size="11" fill="{p["inkMuted"]}">{esc(v["owner"][:1].lower())}-1-{number}</text>'
                f'<text x="{cw - 16}" y="27" text-anchor="end" class="h" font-size="19" fill="{p["inkMuted"]}">vol. {ROMAN[i]}</text>')
    author = (f'<rect x="{cx - 14}" y="{last + 10:.1f}" width="28" height=".8" fill="{ink}" opacity=".45"/>'
              f'<text x="{cx}" y="{last + 27:.1f}" text-anchor="middle" class="m" font-size="12" letter-spacing="1.2" fill="{p["inkMuted"]}">'
              f'{esc(clip_text("jbmono", v["owner"], 12, cw - 40))}</text>')
    jacket = (f'<rect width="{cw}" height="{ch}" fill="{p["paper"]}"/>' + art
              + f'<rect width="{cw}" height="{top + 26:.1f}" fill="url(#bf{i})"/>'
              + petals
              + f'<rect width="{cw}" height="{ch}" filter="url(#paperG)" opacity=".07"/>'
              # the jacket's fold round the spine, on the right
              f'<path d="M{cw - 7},0 V{ch}" stroke="#000" stroke-opacity=".08"/><path d="M{cw - 8.2},0 V{ch}" stroke="#fff" stroke-opacity=".2"/>'
              + head_row + title + author)
    note = ""
    if (today - v["pushed"]).days <= FRESH_DAYS:   # a note in a shop assistant's hand, taped on: still being written
        note = (f'<g transform="translate({cw - 46} {oy - 22}) rotate(7)">'
                f'<rect x="-26" y="-15" width="54" height="34" fill="#000" opacity=".18"/>'
                f'<rect x="-28" y="-17" width="54" height="34" fill="#fff7cf"/>'
                f'<rect x="-12" y="-22" width="24" height="9" fill="{p["blossom"]}" opacity=".6" transform="rotate(-5)"/>'
                f'<text x="-1" y="0" text-anchor="middle" class="h" font-size="18" fill="#c8281e">new</text>'
                f'<text x="-1" y="12" text-anchor="middle" class="h" font-size="12.5" fill="{ink}">chapter!</text></g>')
    # the obi: the description as its copy in bold, the stars in a round badge on the right, the language at the foot
    badge = ""
    bw = cw - 28
    if v["stars"]:
        bw -= 62
        bx, by, on = cw - 39, oy + 43, "#fff" if luma(hot) < .5 else "#1d1a14"
        num = fmt(v["stars"])
        ns = min(24, 44 / text_width("outfit", num, 1))
        badge = (f'<circle cx="{bx}" cy="{by}" r="29" fill="{hot}"/>'
                 f'<circle cx="{bx}" cy="{by}" r="25.5" fill="none" stroke="{on}" stroke-opacity=".45" stroke-width=".8"/>'
                 f'<text x="{bx}" y="{by - 12}" text-anchor="middle" class="m" font-size="8.5" fill="{on}">loved by</text>'
                 f'<text x="{bx}" y="{by + ns * .36:.1f}" text-anchor="middle" class="t" font-size="{ns:.1f}" fill="{on}">{num}</text>'
                 f'<text x="{bx}" y="{by + 20}" text-anchor="middle" class="m" font-size="8.5" fill="{on}">'
                 f'reader{"s" if v["stars"] != 1 else ""}</text>')
    bs = 16
    copy = wrap_blurb(v["desc"], bs, bw) or ["(no blurb yet)"]
    if len(copy) > 3:
        copy = copy[:2] + [clip_text("jbmono", copy[2].rstrip(" ,.;:-，。、") + "...", bs, bw)]
    obi = (f'<rect y="{oy}" width="{cw}" height="{ch - oy}" fill="{bg}"/>'
           f'<path d="M{cw - 7},{oy} V{ch}" stroke="#000" stroke-opacity=".1"/>'
           f'<rect y="{oy}" width="{cw}" height="1" fill="#fff" opacity=".45"/>'
           + "".join(f'<text x="14" y="{oy + 28 + j * 19}" class="m" font-size="{bs}" font-weight="700" fill="{oink}">{esc(ln)}</text>'
                     for j, ln in enumerate(copy))
           + badge +
           f'<text x="14" y="{ch - 9}" class="m" font-size="11" fill="{oink}" opacity=".75">{esc(clip_text("jbmono", v["lang"], 11, cw - 28))}</text>')
    glint = (f'<g transform="translate(-120 0)">'
             f'<animateTransform attributeName="transform" type="translate" values="-120 0;-120 0;300 0;300 0" keyTimes="0;.84;.93;1" '
             f'calcMode="spline" keySplines="0 0 1 1;{EASE};0 0 1 1" dur="15s" begin="{3 + i * 1.6:.1f}s" repeatCount="indefinite"/>'
             f'<rect y="-20" width="70" height="{ch + 40}" transform="skewX(-18)" fill="url(#glint)"/></g>')
    about = f"{v['name']}: {v['desc']}" if v["desc"] else v["name"]
    return (f'<clipPath id="wc{i}"><rect width="{cw}" height="{ch}" rx="2"/></clipPath>{fade}',
            f'<title>{esc(about)}</title><g clip-path="url(#wc{i})">{jacket}{obi}<rect width="{cw}" height="{ch}" fill="url(#board)"/>'
            f'<rect width="{cw}" height="{ch}" fill="#000" opacity="{dim}"/>{glint}</g>{note}')


WORKS_W = 1200             # as wide as the other cards
WORKS_TUCK = 60            # how far the picture runs on under the bookcase, so its fade ends behind it
# the golden tree's colours down the picture's right edge, top to bottom (sampled from works.jpg): the card is painted
# with them, so the picture fades into its own light
WORKS_GOLD = ["#fba02e", "#f79c3d", "#f7bb78"]


def tone(c, p):
    """A colour put through the theme's tone curves (toneR/G/B, as the picture's feComponentTransfer tables), so
    what's painted around the picture darkens with it on the dark theme."""
    def curve(v, table):
        t = [float(x) for x in table.split()]
        x = v / 255 * (len(t) - 1)
        i = min(int(x), len(t) - 2)
        return t[i] + (t[i + 1] - t[i]) * (x - i)
    return "#" + "".join(f"{round(255 * curve(v, p[k])):02x}" for v, k in zip(rgb(c), ("toneR", "toneG", "toneB")))
WORKS_M = 22               # the card's margin round the bookcase


def bookcase(p, d, rows, light=""):
    """The bookcase itself, drawn at the origin: rows of bunkobon standing face out, seen square on from in front of
    its middle (DEPTH), so each shelf shows its walls, and its floor or ceiling, in perspective.  `light` is laid
    over the inside of each shelf, behind the books.  Returns (defs, body, width, height)."""
    vols = d["works"]
    cw, ch = COVER_W, COVER_H
    cols = max(2, max(len(r) for r in rows))
    gap, pad, side, crown, plinth, board, head = 14, 16, 18, 16, 12, 20, 30
    W = cols * cw + (cols - 1) * gap + 2 * (pad + side)
    tier = head + ch + board
    H = crown + len(rows) * tier + plinth
    ex, ey = W / 2, H / 2

    def back(x, y, k=DEPTH):     # a point on the front plane, moved back into the case until it shrinks by k
        return ex + (x - ex) * k, ey + (y - ey) * k

    at = 1 - .3 * (1 - DEPTH)    # the books stand a third of the way back
    wood1, b0, b1 = p["wood1"], p["back0"], p["back1"]
    clips, body = [], []
    for t, row in enumerate(rows):
        x0, x1, y0, yf = side, W - side, crown + t * tier, crown + t * tier + head + ch
        (bx0, by0), (bx1, byf) = back(x0, y0), back(x1, yf)
        # inside the opening: the back panel, then the ceiling, floor and walls running back to it
        inner = (f'<rect x="{bx0:.1f}" y="{by0:.1f}" width="{bx1 - bx0:.1f}" height="{byf - by0:.1f}" fill="url(#back)"/>'
                 f'<rect x="{bx0:.1f}" y="{by0:.1f}" width="{bx1 - bx0:.1f}" height="40" fill="url(#under)"/>'
                 f'<path d="{poly((x0, y0), (x1, y0), (bx1, by0), (bx0, by0))}" fill="{mix(b1, "#000", .35)}"/>'
                 f'<path d="{poly((x0, yf), (x1, yf), (bx1, byf), (bx0, byf))}" fill="url(#floor)"/>'
                 f'<path d="{poly((x0, y0), (bx0, by0), (bx0, byf), (x0, yf))}" fill="{mix(b1, "#000", .2)}"/>'
                 f'<path d="{poly((x1, y0), (bx1, by0), (bx1, byf), (x1, yf))}" fill="{mix(b0, "#fff", .06)}"/>'
                 f'<path d="M{x0},{y0} L{bx0:.1f},{by0:.1f} L{bx1:.1f},{by0:.1f} L{x1},{y0} M{x0},{yf} L{bx0:.1f},{byf:.1f} L{bx1:.1f},{byf:.1f} L{x1},{yf} '
                 f'M{bx0:.1f},{by0:.1f} V{byf:.1f} M{bx1:.1f},{by0:.1f} V{byf:.1f}" fill="none" stroke="#000" stroke-opacity=".18"/>')
        n = len(row)
        x = W / 2 - (n * cw + (n - 1) * gap) / 2
        shadows, books = [], []
        for k, v in enumerate(row):
            i = sum(len(r) for r in rows[:t]) + k
            twins = sum(1 for u in vols[:i] if u["lang"] == v["lang"])
            number = 1 + sum(1 for u in vols[:i] if u["owner"] == v["owner"])
            clip, art = cover(p, i, v, d["today"], .14 * twins, number, i + t)   # each shelf starts one obi colour on
            clips.append(clip)
            bx, by = back(x, yf - ch, at)                      # the book, set back a little from the shelf's edge
            # its shadow on the back panel, down and to the right of the light, and where it meets the shelf
            sx, sy = back(x, yf - ch)
            shadows.append(f'<rect x="{sx + 9:.1f}" y="{sy + 7:.1f}" width="{cw * DEPTH:.1f}" height="{ch * DEPTH - 7:.1f}"/>'
                           f'<rect x="{bx + 2:.1f}" y="{by + ch * at - 5:.1f}" width="{cw * at + 4:.1f}" height="9" rx="4"/>')
            books.append(f'<g transform="translate({bx:.1f} {by:.1f}) scale({at:.4f})"><g class="cv" style="animation-delay:{.2 + i * .15:.2f}s">{art}</g></g>')
            x += cw + gap
        if not vols and t == 0:
            books.append(f'<text x="{W / 2}" y="{yf - ch / 2:.0f}" text-anchor="middle" class="h" font-size="28" '
                         f'fill="{p["muted"]}">nothing pinned yet</text>')
        landed = .2 + (sum(len(r) for r in rows[:t]) + n) * .15 + .6
        clips.append(f'<clipPath id="tier{t}"><rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{yf - y0}"/></clipPath>')
        body.append(f'<g clip-path="url(#tier{t})">{inner}{light}'
                    f'<g class="late" style="animation-delay:{landed:.2f}s"><g fill="#000" opacity=".4" filter="url(#wshade)">{"".join(shadows)}</g></g></g>'
                    + "".join(books)
                    # the shelf's front edge
                    + f'<rect x="{x0}" y="{yf}" width="{x1 - x0}" height="{board}" fill="url(#wood)"/>'
                    f'<rect x="{x0}" y="{yf}" width="{x1 - x0}" height="1.2" fill="#fff" opacity=".3"/>'
                    f'<path d="M{x0},{yf + board * .45:.1f} C{W * .35:.0f},{yf + board * .45 - 1.5:.1f} {W * .6:.0f},{yf + board * .45 + 2:.1f} {x1},{yf + board * .45:.1f}" '
                    f'fill="none" stroke="{p["woodLine"]}" stroke-opacity=".25" stroke-width=".8"/>')
    frame = (f'<rect width="{side}" height="{H}" fill="url(#post)"/><rect x="{W - side}" width="{side}" height="{H}" fill="url(#post)"/>'
             f'<rect width="{W}" height="{crown}" fill="url(#wood)"/><rect width="{W}" height="1.2" fill="#fff" opacity=".3"/>'
             f'<rect y="{H - plinth}" width="{W}" height="{plinth}" fill="{mix(wood1, "#000", .15)}"/>'
             f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="2" fill="none" stroke="{p["woodLine"]}" stroke-opacity=".5"/>')
    return "".join(clips), "".join(body) + frame, W, H


def works_card(theme, d):
    """Chapter ii: Tooko under the golden tree, holding a red book to her chest (scripts/works.jpg), fading into a
    two-shelf bookcase of the pinned repositories as bunkobon - the top shelf takes the odd one, and the case is two
    or three books wide - with white petals drifting down across both.  The books keep their full size, so their
    print stays legible."""
    p = PAL[theme]
    vols = d["works"]
    half = (len(vols) + 1) // 2
    rows = [vols[:half], vols[half:]]
    dark = theme == "dark"
    # the bookcase is made of the same light as the picture: honey-coloured wood and a pale gold back, toned with it
    pw = dict(p, wood0=tone("#e2ae62", p), wood1=tone("#b67a38", p), woodLine=tone("#7a4a1c", p),
              back0=tone("#f9e2a8", p), back1=tone("#eec07a", p))
    # dappled shade of blossom and a few bright patches, falling inside the shelves behind the books
    rnd = random.Random(21)
    dapple = "".join(f'<path d="{BLOSSOM_PETAL}" transform="translate({rnd.uniform(0, 700):.0f} {rnd.uniform(0, 700):.0f}) '
                     f'rotate({rnd.uniform(0, 360):.0f}) scale({rnd.uniform(5, 9):.1f})"/>' for _ in range(14))
    spots = "".join(f'<ellipse cx="{rnd.uniform(0, 700):.0f}" cy="{rnd.uniform(0, 700):.0f}" rx="{rnd.uniform(40, 80):.0f}" '
                    f'ry="{rnd.uniform(25, 45):.0f}"/>' for _ in range(5))
    light = (f'<g fill="{tone("#8a4a10", p)}" opacity=".16" filter="url(#dapple)">{dapple}</g>'
             f'<g fill="{tone("#ffe9a6", p)}" opacity=".3" filter="url(#dapple)">{spots}</g>')
    case_defs, case, cw, chh = bookcase(pw, d, rows, light)
    W, M = WORKS_W, WORKS_M
    H = chh + 2 * M
    cx, cy = W - M - cw, M
    IW = cx + WORKS_TUCK         # works.jpg (930x1092), pinned to the top left and cut to fill up to the bookcase
    petals = []
    for k in range(7):   # white blossom drifting from the tree, down and to the right, across the bookcase
        x0, dur = rnd.uniform(-40, W * .55), rnd.uniform(14, 22)
        beg, s, spin = -rnd.uniform(0, dur), rnd.uniform(1.6, 2.6), rnd.uniform(0, 360)
        petals.append(f'<g opacity="{rnd.uniform(.55, .85):.2f}"><animateTransform attributeName="transform" type="translate" '
                      f'values="{x0:.0f} -20;{x0 + W * .22:.0f} {H * .5:.0f};{x0 + W * .45:.0f} {H + 20}" dur="{dur:.1f}s" begin="{beg:.1f}s" repeatCount="indefinite"/>'
                      f'<path d="{BLOSSOM_PETAL}" transform="translate(1 2) scale({s:.2f})" fill="#6b4a1a" opacity=".25">'
                      f'<animateTransform attributeName="transform" type="rotate" values="{spin:.0f};{spin + 220:.0f};{spin + 360:.0f}" additive="sum" '
                      f'dur="{dur:.1f}s" begin="{beg:.1f}s" repeatCount="indefinite"/></path>'
                      f'<path d="{BLOSSOM_PETAL}" transform="scale({s:.2f})" fill="#fffaf0">'
                      f'<animateTransform attributeName="transform" type="rotate" values="{spin:.0f};{spin + 220:.0f};{spin + 360:.0f}" additive="sum" '
                      f'dur="{dur:.1f}s" begin="{beg:.1f}s" repeatCount="indefinite"/></path></g>')
    css = (fontface("caveat") + ".h{font-family:'Caveat',cursive;font-weight:600}"
           "@keyframes up{from{opacity:0;transform:translateY(28px)}to{opacity:1;transform:none}}"
           ".cv{animation:up .8s cubic-bezier(.3,.7,.4,1) both}"
           "@keyframes late{from{opacity:0}to{opacity:1}}.late{animation:late .8s ease both}")
    label = esc(f"works in progress: Tooko holding a book beside a bookcase of {len(vols)} pinned repositories: "
                f"{', '.join(v['name'] for v in vols) or 'none yet'}")
    wood0, wood1, b0, b1 = pw["wood0"], pw["wood1"], pw["back0"], pw["back1"]
    gold = [tone(c, p) for c in WORKS_GOLD]
    glow = tone("#ffe9a6", p)
    # the tree's light: shafts of sun from the upper left, across the picture and the card behind the bookcase
    sun_defs, sun = light_rays("sunW", 80, W - 80, H, dark, seed=5, count=5)

    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="{label}">'
            + f'<defs><style><![CDATA[{CSS}{css}]]></style>{case_defs}'
            f'<clipPath id="wcard"><rect width="{W}" height="{H}" rx="16"/></clipPath>'
            f'<linearGradient id="wbg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{gold[0]}"/>'
            f'<stop offset=".5" stop-color="{gold[1]}"/><stop offset="1" stop-color="{gold[2]}"/></linearGradient>'
            f'<filter id="wglow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="45"/></filter>'
            f'<filter id="dapple" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="6"/></filter>'
            f'<linearGradient id="haze" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{glow}" stop-opacity=".55"/>'
            f'<stop offset="1" stop-color="{glow}" stop-opacity="0"/></linearGradient>{sun_defs}'
            f'<linearGradient id="wfade" gradientUnits="userSpaceOnUse" x1="{IW - 220}" y1="0" x2="{IW}" y2="0">{smooth_fade()}</linearGradient>'
            f'<mask id="wmask"><rect width="{IW}" height="{H}" fill="url(#wfade)"/></mask>'
            f'<filter id="wtint" color-interpolation-filters="sRGB"><feComponentTransfer><feFuncR type="table" tableValues="{p["toneR"]}"/>'
            f'<feFuncG type="table" tableValues="{p["toneG"]}"/><feFuncB type="table" tableValues="{p["toneB"]}"/></feComponentTransfer></filter>'

            f'<filter id="caseShade" x="-10%" y="-10%" width="120%" height="130%"><feGaussianBlur stdDeviation="9"/></filter>'
            f'<linearGradient id="board" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".12"/>'
            f'<stop offset=".45" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".14"/></linearGradient>'
            # watercolour: ragged, bleeding edges; and the jacket paper's grain
            f'<filter id="wash" x="-30%" y="-30%" width="160%" height="160%"><feTurbulence type="fractalNoise" baseFrequency=".035" numOctaves="3" seed="4"/>'
            f'<feDisplacementMap in="SourceGraphic" scale="30" xChannelSelector="R" yChannelSelector="G"/><feGaussianBlur stdDeviation="3"/></filter>'
            f'<filter id="paperG" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency=".9" numOctaves="2" stitchTiles="stitch"/>'
            f'<feColorMatrix type="saturate" values="0"/></filter>'
            f'<linearGradient id="glint" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#fff" stop-opacity="0"/>'
            f'<stop offset=".5" stop-color="#fff" stop-opacity="{p["glintO"]}"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
            f'<linearGradient id="wood" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{wood0}"/><stop offset="1" stop-color="{wood1}"/></linearGradient>'
            f'<linearGradient id="post" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{wood1}"/><stop offset=".5" stop-color="{wood0}"/>'
            f'<stop offset="1" stop-color="{wood1}"/></linearGradient>'
            f'<linearGradient id="floor" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="{mix(wood0, "#fff", .1)}"/><stop offset="1" stop-color="{mix(wood1, "#000", .1)}"/></linearGradient>'
            f'<linearGradient id="back" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{b0}"/><stop offset="1" stop-color="{b1}"/></linearGradient>'
            f'<linearGradient id="under" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#000" stop-opacity=".45"/><stop offset="1" stop-color="#000" stop-opacity="0"/></linearGradient>'
            f'<filter id="wshade" x="-20%" y="-10%" width="140%" height="120%"><feGaussianBlur stdDeviation="5"/></filter></defs>'
            + f'<g clip-path="url(#wcard)">'
            # the tree's light, all across the card: its colours, and soft patches of sun through the leaves
            f'<rect width="{W}" height="{H}" fill="url(#wbg)"/>'
            f'<g fill="{glow}" filter="url(#wglow)"><ellipse cx="{W * .62:.0f}" cy="{H * .18:.0f}" rx="260" ry="150" opacity=".55"/>'
            f'<ellipse cx="{W * .95:.0f}" cy="{H * .55:.0f}" rx="200" ry="260" opacity=".4"/>'
            f'<ellipse cx="{W * .7:.0f}" cy="{H * .95:.0f}" rx="320" ry="120" opacity=".45"/></g>'
            f'<image href="data:image/jpeg;base64,{WORKS_IMG}" width="{IW}" height="{H}" preserveAspectRatio="xMinYMin slice" mask="url(#wmask)" filter="url(#wtint)"/>'
            + sun +   # behind the bookcase, so the light never dims the books' print
            f'<rect x="{cx + 8}" y="{cy + 12}" width="{cw}" height="{chh}" fill="#000" opacity=".35" filter="url(#caseShade)"/>'
            f'<g transform="translate({cx} {cy})">{case}<rect x="-10" width="120" height="{chh}" fill="url(#haze)"/></g>'
            + "".join(petals) + "</g>"
            f'<rect x="0.75" y="0.75" width="{W - 1.5}" height="{H - 1.5}" rx="16" fill="none" stroke="{p["border"]}" stroke-width="1.5"/></svg>')


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
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="contribution snake of {esc(LOGIN)}">'
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
        with open(path, encoding="utf-8") as fh:
            raw = fh.read()
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
            if name not in ("toc", "works"):   # a book page with a curled corner, and a bookcase: no binder holes
                # the shelf's holes go down the right edge, past the vase, so the row of books starts on a clean edge
                svg = punch(svg, theme == "dark", side="right" if name == "shelf" else "left")
            write_svg(path, svg)
            print(f"wrote {path} ({os.path.getsize(path)//1024} KB)")
    print(json.dumps(d, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
