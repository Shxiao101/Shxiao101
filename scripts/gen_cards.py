#!/usr/bin/env python3
"""Render the profile's stats panel and contribution calendar as themed SVGs.

Runs in GitHub Actions (see .github/workflows/cards.yml) and writes
dist/stats-{dark,light}.svg and dist/calendar-{dark,light}.svg.
`gen_cards.py snake` instead frames the dist/snake-{dark,light}.svg that Platane/snk produced
in the same card as the calendar (no token needed).
Only the standard library is used. Fonts are embedded from scripts/fonts.json,
the panel illustration from scripts/stats.jpg (see prep_images.py).
"""
import base64
import datetime as dt
import json
import os
import re
import sys
import urllib.request

from paper import punch

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
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false, orderBy: {field: STARGAZERS, direction: DESC}) {
      totalCount
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name } }
        }
      }
    }
    contributionsCollection {
      totalCommitContributions
      restrictedContributionsCount
      totalRepositoriesWithContributedCommits
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
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


def collect():
    u = gql(QUERY, {"login": LOGIN})["user"]
    repos = u["repositories"]["nodes"]
    skip = {"XSLT", "Makefile", "DTrace", "HTML", "Shell", "Batchfile", "CMake"}
    langs = {}
    for r in repos:
        for e in r["languages"]["edges"]:
            if e["node"]["name"] in skip:
                continue
            langs[e["node"]["name"]] = langs.get(e["node"]["name"], 0) + e["size"]
    total_lang = sum(langs.values()) or 1
    top = sorted(langs.items(), key=lambda kv: -kv[1])[:6]
    cc = u["contributionsCollection"]
    weeks = [[(d["date"], d["contributionCount"]) for d in w["contributionDays"]]
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
        "active_days": sum(1 for _, c in days if c > 0),
        "days_count": len(days),
        "weeks": weeks,
        "langs": [(n, s / total_lang) for n, s in top],
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
        spark="#fff2b0", toneR="0 .5 .9", toneG="0 .46 .82", toneB="0 .4 .7"),
    "light": dict(
        bg0="#fffdf3", bg1="#f8f2d8", border="#e6dcae",
        title="#3b340c", label="#6f6434", value="#3b340c", muted="#8f8454",
        accent="#a8841a", accent2="#6f7a1a", track="#eee5bf",
        levels=["#f1e7d3", "#f8c89a", "#f08a4b", "#d9481c", "#a82a10"],   # maple: pale amber to vermilion to deep red
        langs=["#a8841a", "#d4b64a", "#6f7a1a", "#3f8f7f", "#d49a5a", "#5e4c0c"],
        grad0="#3b340c", grad1="#a8841a",
        pbg0="#faf4d9", pbg1="#fffdf3", pbg2="#f0f2df", frame="#8a7a1a", frameO=".18", grainO=".03",
        blobA="#f2e173", blobAo=".50", blobB="#d8e3a4", blobBo=".55", blobC="#e6dcf5", blobCo=".70",
        spark="#b8921c", toneR="0 1", toneG="0 1", toneB="0 1"),
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
</defs>
<g clip-path="url(#pcard)">
<rect width="{W}" height="{H}" fill="url(#pbg)"/>
<g filter="url(#pblur)">
<ellipse cx="300" cy="60" rx="380" ry="170" fill="{p['blobA']}" opacity="{p['blobAo']}"><animate attributeName="cx" values="300;400;300" dur="18s" repeatCount="indefinite"/></ellipse>
<ellipse cx="160" cy="470" rx="320" ry="140" fill="{p['blobB']}" opacity="{p['blobBo']}"/>
<ellipse cx="820" cy="300" rx="240" ry="220" fill="{p['blobC']}" opacity="{p['blobCo']}"><animate attributeName="rx" values="240;290;240" dur="15s" repeatCount="indefinite"/></ellipse>
</g>
<image href="data:image/jpeg;base64,{STATS_IMG}" x="{ix}" y="0" width="{IW}" height="{H}" preserveAspectRatio="xMidYMid slice" mask="url(#pmask)" filter="url(#ptint)"/>
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
    W, H = 1200, 280
    x0, y0, cell, gap = 48, 78, 16, 4
    step = cell + gap
    weeks = d["weeks"]
    mx = max((c for w in weeks for _, c in w), default=0)

    def level(c):
        if c <= 0:
            return 0
        if mx <= 4:
            return min(c, 4)
        return min(4, 1 + int(3 * (c - 1) / max(mx - 1, 1) + 1e-9) if c < mx else 4)

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
        for date, count in week:
            di = dt.date.fromisoformat(date).weekday()  # mon=0 … sun=6
            di = (di + 1) % 7  # sun=0 … sat=6, like github
            y = y0 + di * step
            cells.append(f'<rect class="c" x="{x}" y="{y}" width="{cell}" height="{cell}" rx="3.5" fill="{p["levels"][level(count)]}" style="animation-delay:{wi*0.018:.3f}s"><title>{date}: {count}</title></rect>')
    # language bar
    by, bh, bx0, bx1 = 238, 8, x0, W - x0
    bw = bx1 - bx0
    segs, legend = [], []
    x = bx0
    lx = bx0
    for i, (name, share) in enumerate(d["langs"]):
        w = bw * share
        col = p["langs"][i % len(p["langs"])]
        segs.append(f'<rect x="{x:.1f}" y="{by}" width="{max(w-2,0):.1f}" height="{bh}" fill="{col}"/>')
        x += w
        txt = f"{name} {share*100:.1f}%"
        legend.append(f'<circle cx="{lx+4}" cy="{by+26}" r="4" fill="{col}"/>'
                      f'<text x="{lx+14}" y="{by+30}" class="m" font-size="11" fill="{p["label"]}">{txt}</text>')
        lx += 14 + len(txt) * 6.6 + 22
    bar = (f'<clipPath id="bc"><rect x="{bx0}" y="{by}" width="{bw}" height="{bh}" rx="4"/></clipPath>'
           f'<g clip-path="url(#bc)"><rect x="{bx0}" y="{by}" width="{bw}" height="{bh}" fill="{p["track"]}"/>'
           f'<g class="b">{"".join(segs)}</g></g>' + "".join(legend))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="contribution calendar of {LOGIN}">'
            + card_frame(p, W, H, "C")
            + f'<g transform="translate(58 34)" fill="{p["accent"]}">{ICON["star"]}</g>'
            + f'<text x="76" y="40" class="t" font-size="19" fill="url(#tgC)">contributions</text>'
            + f'<text x="{W-x0}" y="40" class="m" font-size="12" text-anchor="end" fill="{p["label"]}">{fmt(d["total"])} contributions · {d["active_days"]} active days · last 12 months</text>'
            + "".join(labels) + "".join(cells) + bar + "</svg>")


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
        for name, fn in (("stats", stats_panel), ("calendar", calendar_card)):
            path = os.path.join(OUT, f"{name}-{theme}.svg")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(punch(fn(theme, d), theme == "dark"))
            print(f"wrote {path} ({os.path.getsize(path)//1024} KB)")
    print(json.dumps({k: v for k, v in d.items() if k != "weeks"}, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
