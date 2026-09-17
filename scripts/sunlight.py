"""Soft shafts of light drifting across a card.

Wide, blurred shafts lean along the light's direction, taper out at both ends, and each one fades in, glides
sideways and fades out again, staggered so some are always passing.
Warm multiply on the light theme (sunlit gold on the paper), screen on the dark theme (a glow).
Standard library only; imported by gen_hero.py and gen_cards.py.
"""
import random


def light_rays(uid, x_from, x_to, h, skew, drift, dark, seed=1, count=4):
    """Defs and body.  Shafts are spread over x_from..x_to (measured at mid-height), lean by `skew` degrees
    and glide `drift` px (sign = direction) over their lifetime.  `uid` keeps ids unique in the document."""
    rnd = random.Random(seed)
    color, blend = ("#ffe9a8", "screen") if dark else ("#f0bd45", "multiply")
    defs = (f'<linearGradient id="{uid}Fall" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="{color}" stop-opacity="0"/><stop offset=".18" stop-color="{color}"/>'
            f'<stop offset=".62" stop-color="{color}" stop-opacity=".55"/><stop offset="1" stop-color="{color}" stop-opacity="0"/>'
            f'</linearGradient>'
            f'<filter id="{uid}Soft" x="-150%" y="-10%" width="400%" height="120%"><feGaussianBlur stdDeviation="18 3"/></filter>')
    shafts = []
    for i in range(count):
        x = x_from + (i + rnd.uniform(.15, .85)) / count * (x_to - x_from)
        w = rnd.uniform(70, 140)
        peak = rnd.uniform(.13, .19) if dark else rnd.uniform(.18, .26)
        dur = rnd.uniform(11, 18)
        begin = -rnd.uniform(0, dur)
        travel = drift * rnd.uniform(.7, 1.3)
        shafts.append(
            f'<g transform="translate({x:.0f} {h / 2:.0f})"><g opacity="0">'
            f'<animate attributeName="opacity" values="0;{peak:.2f};{peak:.2f};0" keyTimes="0;.3;.7;1" dur="{dur:.1f}s" begin="{begin:.1f}s" repeatCount="indefinite"/>'
            f'<animateTransform attributeName="transform" type="translate" values="{-travel / 2:.0f} 0;{travel / 2:.0f} 0" dur="{dur:.1f}s" begin="{begin:.1f}s" repeatCount="indefinite"/>'
            f'<rect x="{-w / 2:.1f}" y="{-h / 2 - 40:.0f}" width="{w:.1f}" height="{h + 80:.0f}" transform="skewX({skew})" '
            f'fill="url(#{uid}Fall)" filter="url(#{uid}Soft)"/></g></g>')
    return defs, f'<g style="mix-blend-mode:{blend}">{"".join(shafts)}</g>'
