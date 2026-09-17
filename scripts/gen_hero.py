#!/usr/bin/env python3
"""Regenerate assets/hero-*.svg, divider-*.svg and footer-*.svg.

Usage:  python scripts/gen_hero.py      (needs fontTools + brotli for text measuring)
Fonts come from scripts/fonts.json (Google Fonts subsets), the art from scripts/{hero,footer}.jpg
(see prep_images.py).  Edit the text block below to change the wording.
"""
import json, base64, io, os, random
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTFont
from paper import punch
from sunlight import light_rays

# ---- text ----------------------------------------------------------------------------------------
NAME = "Shxiao101"
GREETING = "hi there, i'm"
TAGLINE = "code, books, and quiet afternoons"
PILLS = ["Byr Docs", "computer science", "always reading"]
FOOT_LINE = "thanks for stopping by"
FOOT_SUB = "Shxiao  ·  Amano Tooko"
# --------------------------------------------------------------------------------------------------

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "assets")
os.makedirs(OUT, exist_ok=True)
fonts = json.load(open(os.path.join(HERE, "fonts.json"), encoding="utf-8"))
hero_b64 = base64.b64encode(open(os.path.join(HERE, "hero.jpg"), "rb").read()).decode()
foot_b64 = base64.b64encode(open(os.path.join(HERE, "footer.jpg"), "rb").read()).decode()

_ttf = {}
def ttf(key):
    if key not in _ttf:
        _ttf[key] = TTFont(io.BytesIO(base64.b64decode(fonts[key]["b64"])))
    return _ttf[key]

def width(key, text, size, letter_spacing=0.0):
    f = ttf(key); cmap = f.getBestCmap(); hmtx = f["hmtx"]; upem = f["head"].unitsPerEm
    total = 0.0
    for ch in text:
        g = cmap.get(ord(ch))
        total += hmtx[g][0] / upem * size if g is not None else size * 0.6
        total += letter_spacing
    return total

def fontface(key):
    f = fonts[key]
    return ("@font-face{font-family:'%s';font-style:%s;font-weight:%s;"
            "src:url(data:font/woff2;base64,%s) format('woff2');}\n"
            % (f["family"], f["style"], f["weight"], f["b64"]))

# Palette pulled from the illustration: sun-bleached cream, window-light gold, olive frames.
PAL = {
 "dark": dict(
   bg0="#121210", bg1="#1b180e", bg2="#0d1413",
   blob1="#c9a227", blob2="#f2e173", blob3="#2f6b62", blob4="#e8c872",
   blob1o=".34", blob2o=".14", blob3o=".34", blob4o=".12",
   name0="#ffffff", name1="#fbf0c2", name2="#e4cf5a", nameGlow="#c9a227", glowO=".55",
   over="#dcc964", tag="#f5ecc8",
   pillStroke="#b8a646", pillFill="#c9a227", pillFillO=".14", pillText="#f3e9b8",
   beam="#f7e58a", beamO=".10", dust="#fff4c4", dustO="1", spark="#fff2b0",
   border="#e8d98a", borderO=".20", grainO=".045", cursor="#e4cf5a", imgBottom=".35",
   imgTint="0.97 0 0 0 0  0 0.93 0 0 0  0 0 0.84 0 0  0 0 0 1 0",
   footText="#fbf3d4", footMono="#b3a670",
   footGlow="#c2410c", footGlowO=".20", footToneR="0 .55 .92", footToneG="0 .45 .76", footToneB="0 .32 .55"),
 "light": dict(
   bg0="#fffdf3", bg1="#faf4d9", bg2="#f0f2df",
   blob1="#f2e173", blob2="#fbe2a8", blob3="#d8e3a4", blob4="#f5e9a8",
   blob1o=".55", blob2o=".60", blob3o=".55", blob4o=".70",
   name0="#3b340c", name1="#6b5d12", name2="#a8841a", nameGlow="#f2e173", glowO=".75",
   over="#7a6b12", tag="#4f4516",
   pillStroke="#c7b04a", pillFill="#c9a227", pillFillO=".10", pillText="#5e5214",
   beam="#fff8cf", beamO=".70", dust="#d9bd4a", dustO=".55", spark="#b8921c",
   border="#8a7a1a", borderO=".18", grainO=".03", cursor="#a8841a", imgBottom=".55",
   imgTint="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 1 0",
   footText="#3b340c", footMono="#857a45",
   footGlow="#fbd09a", footGlowO=".45", footToneR="0 1", footToneG="0 1", footToneB="0 1"),
}

def star(s):
    k = s * 0.22
    return f"M0,{-s:.1f} L{k:.1f},{-k:.1f} L{s:.1f},0 L{k:.1f},{k:.1f} L0,{s:.1f} L{-k:.1f},{k:.1f} L{-s:.1f},0 L{-k:.1f},{-k:.1f} Z"

def smooth_fade(n=10):
    """Smoothstep opacity ramp 1 -> 0.  A linear ramp stops dead where the picture ends and the eye reads
    that kink as a hard edge on the dark theme; smoothstep eases out to a flat tail."""
    stops = []
    for i in range(n + 1):
        t = i / n
        stops.append(f'<stop offset="{t:.2f}" stop-color="#fff" stop-opacity="{1 - (3*t*t - 2*t*t*t):.3f}"/>')
    return "".join(stops)

FADE_OUT = smooth_fade()

W, H = 1200, 480
IMG_W = 560                       # hero.jpg is 1008x864 -> 560x480
TX = 612                          # text column starts just past the picture
TAG_SIZE, FOOT_SIZE = 42, 38      # Caveat runs small; this matches the letter height of the old 33/30px serif

# hero intro, played once per page load: type the greeting, then the name, then hand-write the tagline
TYPE_START = .5                   # s before the first keystroke
GREET_KEY, NAME_KEY = .065, .13   # s per keystroke (jittered a little so it doesn't feel mechanical)
LINE_PAUSE, WRITE_PAUSE = .35, .3
WRITE_SPEED = 230                 # px of handwriting per second

BASE_CSS = """
.over{font-family:'JetBrains Mono',monospace;font-weight:500;font-size:14px;letter-spacing:2.5px}
.name{font-family:'Outfit',sans-serif;font-weight:800;font-size:92px;letter-spacing:-2px}
.pill{font-family:'JetBrains Mono',monospace;font-weight:500;font-size:13px}
.foot-en{font-family:'Caveat',cursive;font-weight:600;font-size:%dpx}
""" % FOOT_SIZE

GRAIN = ('<filter id="grain" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" '
         'baseFrequency="0.85" numOctaves="2" stitchTiles="stitch"/><feColorMatrix type="saturate" values="0"/></filter>')

def dust(p, w, h, seed=7, n=26):
    """Motes drifting up and sideways through the window light: a few soft blurred ones, many small sharp ones."""
    rnd = random.Random(seed)
    soft, sharp = [], []
    for i in range(n):
        cx = rnd.uniform(20, w - 20); cy = rnd.uniform(20, h - 20)
        dx = rnd.uniform(-22, 30); dy = -rnd.uniform(16, 52)
        dur = rnd.uniform(10, 22); beg = -rnd.uniform(0, 14)
        anim = (f'<animateTransform attributeName="transform" type="translate" values="0 0;{dx:.0f} {dy:.0f};0 0" '
                f'dur="{dur:.1f}s" begin="{beg:.1f}s" repeatCount="indefinite"/>')
        if i % 3 == 0:
            r = rnd.uniform(6, 20); o = rnd.uniform(0.12, 0.40) * float(p["dustO"])
            soft.append(f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="{r:.1f}" opacity="{o:.2f}">{anim}</circle>')
        else:
            r = rnd.uniform(1.0, 2.6); o = rnd.uniform(0.35, 0.85) * float(p["dustO"])
            tw = rnd.uniform(2.5, 5.5)
            sharp.append(f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="{r:.1f}" opacity="{o:.2f}">{anim}'
                         f'<animate attributeName="fill-opacity" values="1;.25;1" dur="{tw:.1f}s" begin="{beg:.1f}s" repeatCount="indefinite"/></circle>')
    return (f'<g filter="url(#blur9)" fill="{p["dust"]}">' + "".join(soft) + "</g>"
            f'<g fill="{p["dust"]}">' + "".join(sharp) + "</g>")

def beams(p, xs, h, angle=24, seed=3):
    """Slanted shafts of sunlight that slowly breathe."""
    rnd = random.Random(seed)
    out = []
    for x in xs:
        bw = rnd.uniform(46, 110); dur = rnd.uniform(7, 12); beg = -rnd.uniform(0, 6)
        o = float(p["beamO"])
        out.append(
            f'<rect x="{x:.0f}" y="-120" width="{bw:.0f}" height="{h+240}" transform="rotate({angle} {x:.0f} 0)" opacity="{o*.6:.2f}">'
            f'<animate attributeName="opacity" values="{o*.35:.2f};{o:.2f};{o*.35:.2f}" dur="{dur:.1f}s" begin="{beg:.1f}s" repeatCount="indefinite"/></rect>')
    return f'<g filter="url(#blur18)" fill="{p["beam"]}">' + "".join(out) + "</g>"

SPARKS = [(1128,76,9,3.1,0.0),(1150,300,8,2.6,0.8),(660,52,6,3.6,1.5),(1090,428,7,2.9,0.4),(498,64,7,3.3,2.1),(930,40,5,2.4,1.1),(1136,196,5,3.8,0.6)]
def sparkles(p):
    out = []
    for (x, y, s, dur, beg) in SPARKS:
        out.append(
            f'<g transform="translate({x} {y})"><path d="{star(s)}" fill="{p["spark"]}">'
            f'<animate attributeName="opacity" values="0.15;1;0.15" dur="{dur}s" begin="{beg}s" repeatCount="indefinite"/>'
            f'<animateTransform attributeName="transform" type="scale" values="0.7;1.15;0.7" dur="{dur}s" begin="{beg}s" repeatCount="indefinite"/>'
            f'</path></g>')
    return "\n".join(out)

def pills(p, x0=TX, y0=326, appear=None):
    """`appear`: fade the pills in one after another from this time (s); they stay visible without SMIL."""
    out = []; x = x0
    for i, t in enumerate(PILLS):
        w = width("jbmono", t, 13) + 28
        fade = ("" if appear is None else
                f'<set attributeName="opacity" to="0" begin="0s" fill="freeze"/>'
                f'<animate attributeName="opacity" from="0" to="1" begin="{appear + i * .15:.2f}s" dur=".5s" fill="freeze"/>')
        out.append(
            f'<g>{fade}<rect x="{x:.1f}" y="{y0}" width="{w:.1f}" height="28" rx="14" fill="{p["pillFill"]}" fill-opacity="{p["pillFillO"]}" '
            f'stroke="{p["pillStroke"]}" stroke-opacity=".75" stroke-width="1"/>'
            f'<text x="{x+14:.1f}" y="{y0+18.5}" class="pill" fill="{p["pillText"]}">{t}</text></g>')
        x += w + 10
    if x - 10 > W - 52:           # stay clear of the binder holes on the right edge
        raise SystemExit(f"pills overflow the banner by {x - 10 - (W - 52):.0f}px; shorten PILLS")
    return "\n".join(out)

def keystrokes(text, key, size, spacing, start, seed):
    """(time, advance so far) for each character, typed at a slightly uneven pace."""
    rnd = random.Random(seed)
    out, t = [], start
    for i in range(1, len(text) + 1):
        out.append((t, width(TYPE_FONTS[size], text[:i], size, letter_spacing=spacing)))
        t += key * rnd.uniform(.7, 1.4)
    return out

TYPE_FONTS = {14: "jbmono", 92: "outfit"}

def reveal(clip_id, x, y, h, full_w, strokes, pad_l, pad_r):
    """Clip that grows one character per keystroke.  Its base width shows the whole line, so a viewer
    without SMIL still sees the text; the set at 0s hides it, later sets outrank it as they begin."""
    sets = "".join(f'<set attributeName="width" to="{pad_l + w + pad_r:.1f}" begin="{t:.2f}s" fill="freeze"/>' for t, w in strokes)
    return (f'<clipPath id="{clip_id}"><rect x="{x - pad_l}" y="{y}" width="{pad_l + full_w + pad_r:.1f}" height="{h}">'
            f'<set attributeName="width" to="0" begin="0s" fill="freeze"/>{sets}</rect></clipPath>')

def handwriting(text, x, baseline, size, color, start):
    """Each Caveat glyph as an outline that is traced like a pen stroke, then inked in.
    Base attributes are the finished glyph (static fallback); the 0s sets blank it before the pen arrives."""
    f = ttf("caveat"); glyphs = f.getGlyphSet(); cmap = f.getBestCmap(); hmtx = f["hmtx"]
    k = size / f["head"].unitsPerEm
    out, pen_x = [], x
    for ch in text:
        name = cmap[ord(ch)]
        pen = SVGPathPen(glyphs); glyphs[name].draw(pen); d = pen.getCommands()
        if d:
            t = start + (pen_x - x) / WRITE_SPEED
            draw = max(.28, hmtx[name][0] * k / WRITE_SPEED * 2.2)
            out.append(
                f'<path transform="translate({pen_x:.1f} {baseline}) scale({k:.5f} {-k:.5f})" d="{d}" pathLength="1" '
                f'fill="{color}" stroke="{color}" stroke-opacity="0" stroke-width="{1.3 / k:.1f}" stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="1 1">'
                f'<set attributeName="fill-opacity" to="0" begin="0s" fill="freeze"/>'
                f'<set attributeName="stroke-opacity" to="1" begin="0s" fill="freeze"/>'
                f'<set attributeName="stroke-dashoffset" to="1" begin="0s" fill="freeze"/>'
                f'<animate attributeName="stroke-dashoffset" from="1" to="0" begin="{t:.2f}s" dur="{draw:.2f}s" fill="freeze"/>'
                f'<animate attributeName="fill-opacity" from="0" to="1" begin="{t + draw * .55:.2f}s" dur=".35s" fill="freeze"/>'
                f'<animate attributeName="stroke-opacity" from="1" to="0" begin="{t + draw:.2f}s" dur=".3s" fill="freeze"/>'
                f'</path>')
        pen_x += hmtx[name][0] * k
    return "\n".join(out)

def hero(theme):
    p = PAL[theme]
    css = "".join(fontface(k) for k in ("outfit", "jbmono")) + BASE_CSS   # the tagline is drawn as glyph paths
    name_w = width("outfit", NAME, 92, letter_spacing=-2)
    cursor_x = TX + name_w + 12
    greet = keystrokes(GREETING, GREET_KEY, 14, 2.5, TYPE_START, seed=1)
    name_start = greet[-1][0] + LINE_PAUSE
    typed = keystrokes(NAME, NAME_KEY, 92, -2, name_start, seed=2)
    name_end = typed[-1][0]
    greet_w = width("jbmono", GREETING, 14, letter_spacing=2.5)
    # cursor: a thin bar on the greeting line, then the tall bar that follows the name and blinks once done;
    # its base attributes are the final resting place after the name
    cur = ('<set attributeName="x" to="{x}" begin="0s" fill="freeze"/><set attributeName="y" to="104" begin="0s" fill="freeze"/>'
           '<set attributeName="width" to="3" begin="0s" fill="freeze"/><set attributeName="height" to="17" begin="0s" fill="freeze"/>').format(x=TX)
    cur += "".join(f'<set attributeName="x" to="{TX + w + 1:.1f}" begin="{t:.2f}s" fill="freeze"/>' for t, w in greet)
    hop = name_start - LINE_PAUSE / 2
    cur += (f'<set attributeName="x" to="{TX}" begin="{hop:.2f}s" fill="freeze"/><set attributeName="y" to="160" begin="{hop:.2f}s" fill="freeze"/>'
            f'<set attributeName="width" to="7" begin="{hop:.2f}s" fill="freeze"/><set attributeName="height" to="64" begin="{hop:.2f}s" fill="freeze"/>')
    cur += "".join(f'<set attributeName="x" to="{TX + w + 12:.1f}" begin="{t:.2f}s" fill="freeze"/>' for t, w in typed)
    cur += f'<animate attributeName="opacity" values="1;1;0;0" keyTimes="0;.5;.5;1" dur="1.1s" begin="{name_end + .15:.2f}s" repeatCount="indefinite"/>'
    # light comes from the girl's window on the left: rays lean down-right and drift rightwards over the text side
    sun_defs, sun = light_rays("sunH", 540, 1160, H, 26, 150, theme == "dark", seed=4)
    clips = (reveal("typeGreet", TX, 96, 30, greet_w, greet, 4, 0)
             + reveal("typeName", TX, 128, 120, name_w, typed, 10, 0)
             + reveal("typeGlow", TX, 70, 220, name_w, typed, 60, 12))
    write_start = name_end + WRITE_PAUSE
    write_end = write_start + width("caveat", TAGLINE, TAG_SIZE) / WRITE_SPEED + .4
    if TX + width("caveat", TAGLINE, TAG_SIZE) > W - 52:
        raise SystemExit(f"TAGLINE is too wide for the banner ({width('caveat', TAGLINE, TAG_SIZE):.0f}px)")
    if cursor_x + 7 > W - 52:
        raise SystemExit(f"NAME is too wide for the banner ({name_w:.0f}px)")
    label = f"{NAME} — {TAGLINE}"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="{label}">
<title>{label}</title>
<defs>
<style><![CDATA[{css}]]></style>
<clipPath id="card"><rect x="0" y="0" width="{W}" height="{H}" rx="28" ry="28"/></clipPath>
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
  <stop offset="0" stop-color="{p['bg1']}"/><stop offset=".45" stop-color="{p['bg0']}"/><stop offset="1" stop-color="{p['bg2']}"/>
</linearGradient>
<linearGradient id="nameGrad" x1="0" y1="0" x2="1" y2="0">
  <stop offset="0" stop-color="{p['name0']}"/><stop offset=".6" stop-color="{p['name1']}"/><stop offset="1" stop-color="{p['name2']}"/>
</linearGradient>
<linearGradient id="fadeH" gradientUnits="userSpaceOnUse" x1="{IMG_W-270}" y1="0" x2="{IMG_W}" y2="0">
{FADE_OUT}
</linearGradient>
<linearGradient id="fadeV" gradientUnits="userSpaceOnUse" x1="0" y1="330" x2="0" y2="{H}">
  <stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="{p['imgBottom']}"/>
</linearGradient>
<mask id="mV"><rect x="0" y="0" width="{IMG_W}" height="{H}" fill="url(#fadeV)"/></mask>
<mask id="mImg"><g mask="url(#mV)"><rect x="0" y="0" width="{IMG_W}" height="{H}" fill="url(#fadeH)"/></g></mask>
<filter id="blur70" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="70"/></filter>
<filter id="blur9" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="9"/></filter>
<filter id="blur18" x="-60%" y="-30%" width="220%" height="160%"><feGaussianBlur stdDeviation="18"/></filter>
<filter id="tint" color-interpolation-filters="sRGB"><feColorMatrix type="matrix" values="{p['imgTint']}"/></filter>
{GRAIN}
{clips}
{sun_defs}
</defs>
<g clip-path="url(#card)">
<rect width="{W}" height="{H}" fill="url(#bg)"/>
<g filter="url(#blur70)">
<ellipse cx="560" cy="120" rx="360" ry="200" fill="{p['blob1']}" opacity="{p['blob1o']}"><animate attributeName="cx" values="560;660;560" dur="17s" repeatCount="indefinite"/></ellipse>
<ellipse cx="880" cy="-10" rx="340" ry="150" fill="{p['blob2']}" opacity="{p['blob2o']}"><animate attributeName="cy" values="-10;50;-10" dur="21s" repeatCount="indefinite"/></ellipse>
<ellipse cx="1080" cy="470" rx="300" ry="140" fill="{p['blob3']}" opacity="{p['blob3o']}"/>
<ellipse cx="760" cy="300" rx="210" ry="220" fill="{p['blob4']}" opacity="{p['blob4o']}"><animate attributeName="rx" values="210;260;210" dur="14s" repeatCount="indefinite"/></ellipse>
</g>
{beams(p, (560, 720, 905, 1060), H)}
<image href="data:image/jpeg;base64,{hero_b64}" x="0" y="0" width="{IMG_W}" height="{H}" preserveAspectRatio="xMidYMid slice" mask="url(#mImg)" filter="url(#tint)"/>
{sun}
{dust(p, W, H)}
{sparkles(p)}
<rect width="{W}" height="{H}" filter="url(#grain)" opacity="{p['grainO']}"/>
<text x="{TX}" y="118" class="over" fill="{p['over']}" clip-path="url(#typeGreet)">{GREETING}</text>
<g clip-path="url(#typeGlow)"><text x="{TX}" y="222" class="name" fill="{p['nameGlow']}" opacity="{p['glowO']}" filter="url(#blur18)">{NAME}</text></g>
<text x="{TX}" y="222" class="name" fill="url(#nameGrad)" clip-path="url(#typeName)">{NAME}</text>
<rect x="{cursor_x:.1f}" y="160" width="7" height="64" rx="2" fill="{p['cursor']}">{cur}</rect>
{handwriting(TAGLINE, TX, 282, TAG_SIZE, p['tag'], write_start)}
{pills(p, appear=write_end)}
<rect x="1" y="1" width="{W-2}" height="{H-2}" rx="27" fill="none" stroke="{p['border']}" stroke-opacity="{p['borderO']}" stroke-width="1.5"/>
</g>
</svg>
'''

def divider(theme):
    c1 = "#e4cf5a" if theme == "dark" else "#a8841a"
    c2 = "#a0a741" if theme == "dark" else "#6f7a1a"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 28" width="1200" height="28">
<defs>
<linearGradient id="g" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{c1}" stop-opacity="0"/><stop offset=".5" stop-color="{c1}" stop-opacity=".9"/><stop offset="1" stop-color="{c2}" stop-opacity="0"/></linearGradient>
</defs>
<line x1="60" y1="14" x2="1140" y2="14" stroke="url(#g)" stroke-width="1.5"/>
<g transform="translate(600 14)"><path d="{star(7)}" fill="{c1}"><animateTransform attributeName="transform" type="rotate" values="0;90" dur="6s" repeatCount="indefinite"/></path></g>
</svg>
'''

# Stylised five-lobed maple leaf centred on the origin, ~19 units across, stem pointing down.
LEAF = ("M0,-10 L1.5,-6.5 L3.2,-7.2 L2.6,-3.6 L6.8,-5.2 L6,-3.2 L9.2,-2.4 L6.4,.4 L7.2,1.8 L3.4,2 L3.8,4.2 "
        "L.8,3 L.6,7 L-.6,7 L-.8,3 L-3.8,4.2 L-3.4,2 L-7.2,1.8 L-6.4,.4 L-9.2,-2.4 L-6,-3.2 L-6.8,-5.2 "
        "L-2.6,-3.6 L-3.2,-7.2 L-1.5,-6.5 Z")
VEINS = "M0,5 V-7.5 M0,1.5 L6.2,-3.6 M0,1.5 L-6.2,-3.6 M0,3 L5.4,1.4 M0,3 L-5.4,1.4"
LEAF_COLORS = ["#e8430a", "#f47e08", "#d03906", "#c21d0a", "#f7970b", "#faae13", "#e86108"]   # sampled from 001.jpg
EASE = ".45 0 .55 1;.45 0 .55 1"

def leaves(w, h, seed=21):
    """Maple leaves drifting down: each one falls, sways side to side, rocks with the sway and flips over.
    Three depths - small faint far leaves, mid leaves, and a few big soft-focus ones up close."""
    rnd = random.Random(seed)
    layers = ["far"] * 5 + ["mid"] * 9 + ["near"] * 3
    rnd.shuffle(layers)
    out = []
    for i, layer in enumerate(layers):
        x = (i + rnd.uniform(.15, .85)) / len(layers) * (w + 60) - 30
        if layer == "far":
            s, o, fall = rnd.uniform(.85, 1.1), rnd.uniform(.45, .6), rnd.uniform(22, 30)
        elif layer == "mid":
            s, o, fall = rnd.uniform(1.5, 2.0), rnd.uniform(.85, 1), rnd.uniform(15, 21)
        else:
            s, o, fall = rnd.uniform(2.7, 3.3), rnd.uniform(.75, .9), rnd.uniform(11, 15)
        blur = ' filter="url(#leafBlur)"' if layer == "near" else ""
        sway = rnd.uniform(18, 46) * s ** .5
        sdur = rnd.uniform(4.5, 7.5); flip = rnd.uniform(2.6, 4.8)
        tilt = rnd.uniform(25, 50); spin = rnd.uniform(0, 360)
        fbeg = -rnd.uniform(0, fall); sbeg = -rnd.uniform(0, sdur)
        c = rnd.choice(LEAF_COLORS)
        swing = f'keyTimes="0;.5;1" calcMode="spline" keySplines="{EASE}" dur="{sdur:.1f}s" begin="{sbeg:.1f}s" repeatCount="indefinite"'
        out.append(
            f'<g transform="translate({x:.0f} 0)" opacity="{o:.2f}"{blur}>'
            f'<g><animateTransform attributeName="transform" type="translate" values="0 {-14*s:.0f};0 {h+14*s:.0f}" dur="{fall:.1f}s" begin="{fbeg:.1f}s" repeatCount="indefinite"/>'
            f'<g><animateTransform attributeName="transform" type="translate" values="{-sway:.0f} 0;{sway:.0f} 0;{-sway:.0f} 0" {swing}/>'
            f'<g><animateTransform attributeName="transform" type="rotate" values="{spin-tilt:.0f};{spin+tilt:.0f};{spin-tilt:.0f}" {swing}/>'
            f'<g transform="scale({s:.2f})"><use href="#leaf" fill="{c}" stroke="{c}" stroke-width=".8" stroke-linejoin="round">'
            f'<animateTransform attributeName="transform" type="scale" values="1 1;.25 1;1 1" keyTimes="0;.5;1" calcMode="spline" keySplines="{EASE}" dur="{flip:.1f}s" begin="{fbeg:.1f}s" repeatCount="indefinite"/>'
            f'</use></g></g></g></g></g>')
    return "\n".join(out)

def footer(theme):
    p = PAL[theme]
    css = "".join(fontface(k) for k in ("caveat", "jbmono")) + BASE_CSS
    FW, FH = 1200, 380
    IW = 485                      # footer.jpg is 970x760 -> 485x380, pinned to the left edge
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {FW} {FH}" width="{FW}" height="{FH}" role="img" aria-label="{FOOT_LINE}">
<title>{FOOT_LINE}</title>
<defs>
<style><![CDATA[{css}]]></style>
<clipPath id="fcard"><rect x="0" y="0" width="{FW}" height="{FH}" rx="28" ry="28"/></clipPath>
<linearGradient id="fbg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{p['bg1']}"/><stop offset=".5" stop-color="{p['bg0']}"/><stop offset="1" stop-color="{p['bg2']}"/></linearGradient>
<linearGradient id="ffade" gradientUnits="userSpaceOnUse" x1="{IW-330}" y1="0" x2="{IW}" y2="0">
{FADE_OUT}
</linearGradient>
<mask id="fmask"><rect x="0" y="0" width="{IW}" height="{FH}" fill="url(#ffade)"/></mask>
<filter id="blur70" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="70"/></filter>
<filter id="leafBlur" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2"/></filter>
<filter id="ftone" color-interpolation-filters="sRGB"><feComponentTransfer>
  <feFuncR type="table" tableValues="{p['footToneR']}"/><feFuncG type="table" tableValues="{p['footToneG']}"/><feFuncB type="table" tableValues="{p['footToneB']}"/>
</feComponentTransfer></filter>
<g id="leaf"><path d="{LEAF}"/><path d="{VEINS}" fill="none" stroke="#4a1400" stroke-opacity=".35" stroke-width=".45" stroke-linecap="round"/></g>
{GRAIN}
</defs>
<g clip-path="url(#fcard)">
<rect width="{FW}" height="{FH}" fill="url(#fbg)"/>
<g filter="url(#blur70)">
<ellipse cx="470" cy="230" rx="240" ry="190" fill="{p['footGlow']}" opacity="{p['footGlowO']}"><animate attributeName="rx" values="260;310;260" dur="16s" repeatCount="indefinite"/></ellipse>
<ellipse cx="900" cy="10" rx="320" ry="110" fill="{p['blob2']}" opacity="{p['blob2o']}"/>
<ellipse cx="1110" cy="390" rx="300" ry="140" fill="{p['blob3']}" opacity="{p['blob3o']}"><animate attributeName="cy" values="390;350;390" dur="19s" repeatCount="indefinite"/></ellipse>
</g>
<image href="data:image/jpeg;base64,{foot_b64}" x="0" y="0" width="{IW}" height="{FH}" preserveAspectRatio="xMidYMid slice" mask="url(#fmask)" filter="url(#ftone)"/>
{leaves(FW, FH)}
<rect width="{FW}" height="{FH}" filter="url(#grain)" opacity="{p['grainO']}"/>
<text x="{FW-72}" y="196" text-anchor="end" class="foot-en" fill="{p['footText']}">{FOOT_LINE}</text>
<line x1="{FW-252}" y1="248" x2="{FW-72}" y2="248" stroke="{p['border']}" stroke-opacity=".5"/>
<text x="{FW-72}" y="278" text-anchor="end" class="over" fill="{p['footMono']}">{FOOT_SUB}</text>
<rect x="1" y="1" width="{FW-2}" height="{FH-2}" rx="27" fill="none" stroke="{p['border']}" stroke-opacity="{p['borderO']}" stroke-width="1.5"/>
</g>
</svg>
'''


for theme in ("dark", "light"):
    for name, fn in (("hero", hero), ("divider", divider), ("footer", footer)):
        path = os.path.join(OUT, f"{name}-{theme}.svg")
        # hero and footer art sits on the left, so their binder holes go down the right edge
        svg = fn(theme) if name == "divider" else punch(fn(theme), theme == "dark", side="right")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(svg)
        print(f"{path}: {os.path.getsize(path)/1024:.0f} KB")
