"""Pieces shared by gen_hero.py and gen_cards.py: the embedded fonts, the four-point sparkle, the smoothstep fade
and the easing curve.  Standard library only.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = json.load(open(os.path.join(HERE, "fonts.json"), encoding="utf-8"))

EASE = ".45 0 .55 1"          # one keySplines segment; join it with ";" once per interval of the animation


def fontface(key):
    f = FONTS[key]
    return ("@font-face{font-family:'%s';font-style:%s;font-weight:%s;"
            "src:url(data:font/woff2;base64,%s) format('woff2');}\n"
            % (f["family"], f["style"], f["weight"], f["b64"]))


def star_path(s):
    k = s * 0.22
    return f"M0,{-s:.1f} L{k:.1f},{-k:.1f} L{s:.1f},0 L{k:.1f},{k:.1f} L0,{s:.1f} L{-k:.1f},{k:.1f} L{-s:.1f},0 L{-k:.1f},{-k:.1f} Z"


def smooth_fade(n=10, fade_in=False):
    """Smoothstep opacity stops, 1 -> 0 (or 0 -> 1 with fade_in).  A linear ramp stops dead where the picture ends
    and the eye reads that kink as a hard edge on the dark theme; smoothstep eases out to a flat tail."""
    stops = []
    for i in range(n + 1):
        t = i / n
        s = 3*t*t - 2*t*t*t
        stops.append(f'<stop offset="{t:.2f}" stop-color="#fff" stop-opacity="{s if fade_in else 1 - s:.3f}"/>')
    return "".join(stops)


def write_svg(path, svg):
    """LF line endings on every platform, so a run on Windows matches the one in CI."""
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(svg)
