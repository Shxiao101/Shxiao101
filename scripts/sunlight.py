"""Shafts of light and shade drifting across a card.

Wide, blurred bands within a card all lean the same way and drift the same way, so nothing crosses.  Light shafts
alternate with shade bands between them for a clear light/dark contrast; each band fades in, glides sideways
and fades out again, staggered so the pattern keeps shifting.
Light theme: warm gold light and brown shade, both multiplied into the paper.
Dark theme: screen-blended glow for the light, multiplied black for the shade.
Standard library only; imported by gen_hero.py and gen_cards.py.
"""
import random

SKEW = 22          # degrees each band leans
DRIFT = 90         # px each band glides, in the light's direction, over its lifetime
LIFE = (22, 32)    # s per band: fade in, glide, fade out — slow enough to read as drifting sunlight


def light_rays(uid, x_from, x_to, h, dark, from_left=True, seed=1, count=4):
    """Defs and body.  `count` light shafts spread over x_from..x_to (at mid-height), a shade band in each gap.
    from_left: light falls from the upper left to the lower right and drifts right; False mirrors both.
    `uid` keeps ids unique in the document."""
    sign = 1 if from_left else -1
    rnd = random.Random(seed)
    if dark:
        light, light_blend, light_peak = "#ffe9a8", "screen", (.30, .42)
        shade, shade_peak = "#000", (.30, .40)
    else:
        light, light_blend, light_peak = "#f0bd45", "multiply", (.34, .46)
        shade, shade_peak = "#7a5a1c", (.10, .16)

    def fall(name, color):
        return (f'<linearGradient id="{uid}{name}" x1="0" y1="0" x2="0" y2="1">'
                f'<stop offset="0" stop-color="{color}" stop-opacity="0"/><stop offset=".18" stop-color="{color}"/>'
                f'<stop offset=".62" stop-color="{color}" stop-opacity=".6"/><stop offset="1" stop-color="{color}" stop-opacity="0"/>'
                f'</linearGradient>')

    defs = (fall("Light", light) + fall("Shade", shade)
            + f'<filter id="{uid}Soft" x="-150%" y="-10%" width="400%" height="120%"><feGaussianBlur stdDeviation="14 3"/></filter>')

    def band(x, w, peak, grad):
        dur = rnd.uniform(*LIFE)
        begin = -rnd.uniform(0, dur)
        travel = sign * DRIFT * rnd.uniform(.8, 1.2)
        return (f'<g transform="translate({x:.0f} {h / 2:.0f})"><g opacity="0">'
                f'<animate attributeName="opacity" values="0;{peak:.2f};{peak:.2f};0" keyTimes="0;.3;.7;1" dur="{dur:.1f}s" begin="{begin:.1f}s" repeatCount="indefinite"/>'
                f'<animateTransform attributeName="transform" type="translate" values="{-travel / 2:.0f} 0;{travel / 2:.0f} 0" dur="{dur:.1f}s" begin="{begin:.1f}s" repeatCount="indefinite"/>'
                f'<rect x="{-w / 2:.1f}" y="{-h / 2 - 40:.0f}" width="{w:.1f}" height="{h + 80:.0f}" transform="skewX({sign * SKEW})" '
                f'fill="url(#{uid}{grad})" filter="url(#{uid}Soft)"/></g></g>')

    step = (x_to - x_from) / count
    lights, shades = [], []
    for i in range(count):
        x = x_from + (i + rnd.uniform(.3, .7)) * step
        lights.append(band(x, rnd.uniform(80, 150), rnd.uniform(*light_peak), "Light"))
        shades.append(band(x + step / 2, rnd.uniform(90, 170), rnd.uniform(*shade_peak), "Shade"))
    return defs, (f'<g style="mix-blend-mode:multiply">{"".join(shades)}</g>'
                  f'<g style="mix-blend-mode:{light_blend}">{"".join(lights)}</g>')
