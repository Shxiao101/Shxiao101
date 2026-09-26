"""Animated light for the cards: drifting shafts of light and shade (light_rays) or breathing halos (halo).

Shafts: wide, blurred bands within a card all lean the same way and drift the same way, so nothing crosses.  On the
dark theme light shafts alternate with shade bands for a clear light/dark contrast; each band fades in, glides
sideways and fades out again, staggered so the pattern keeps shifting.
Halos: soft radial glows with a faint ring that slowly swell, dim and drift.
Dark theme: screen-blended warm glow (black shade bands).  Light theme: light only, a pale warm white laid over the
paper that brightens it; no multiply and no shade, which read as stains and shadows on the light background.
Standard library only; imported by gen_hero.py and gen_cards.py.
"""
import random

SKEW = 22          # degrees each band leans
DRIFT = 90         # px each band glides, in the light's direction, over its lifetime
LIFE = (22, 32)    # s per band: fade in, glide, fade out — slow enough to read as drifting sunlight


def light_rays(uid, x_from, x_to, h, dark, from_left=True, seed=1, count=4):
    """Defs and body.  `count` light shafts spread over x_from..x_to (at mid-height), plus a shade band in each gap
    on the dark theme.
    from_left: light falls from the upper left to the lower right and drifts right; False mirrors both.
    `uid` keeps ids unique in the document."""
    sign = 1 if from_left else -1
    rnd = random.Random(seed)
    if dark:
        light, light_blend, light_peak = "#ffe9a8", "screen", (.30, .42)
        shade, shade_peak = "#000", (.30, .40)
    else:
        light, light_blend, light_peak = "#ffffff", "normal", (.55, .75)
        shade, shade_peak = None, None

    def fall(name, color):
        return (f'<linearGradient id="{uid}{name}" x1="0" y1="0" x2="0" y2="1">'
                f'<stop offset="0" stop-color="{color}" stop-opacity="0"/><stop offset=".18" stop-color="{color}"/>'
                f'<stop offset=".62" stop-color="{color}" stop-opacity=".6"/><stop offset="1" stop-color="{color}" stop-opacity="0"/>'
                f'</linearGradient>')

    defs = (fall("Light", light) + (fall("Shade", shade) if shade else "")
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
        if shade:
            shades.append(band(x + step / 2, rnd.uniform(90, 170), rnd.uniform(*shade_peak), "Shade"))
    shade_layer = f'<g style="mix-blend-mode:multiply">{"".join(shades)}</g>' if shades else ""
    return defs, shade_layer + f'<g style="mix-blend-mode:{light_blend}">{"".join(lights)}</g>'


def halo(uid, glows, dark):
    """Defs and body for soft halos.  `glows` is a list of (cx, cy, r, ring): each glow breathes (grows ~12% and
    dims) and drifts a little on its own slow cycle; `ring` adds the faint ring a bright light throws around itself."""
    color, blend, core = ("#ffe3a0", "screen", .55) if dark else ("#fffdf2", "normal", .85)
    ease = ".45 0 .55 1;.45 0 .55 1"
    defs = (f'<radialGradient id="{uid}Glow"><stop offset="0" stop-color="{color}"/>'
            f'<stop offset=".3" stop-color="{color}" stop-opacity=".62"/><stop offset=".65" stop-color="{color}" stop-opacity=".2"/>'
            f'<stop offset="1" stop-color="{color}" stop-opacity="0"/></radialGradient>'
            f'<filter id="{uid}Ring" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="7"/></filter>')
    body = []
    for i, (cx, cy, r, ring) in enumerate(glows):
        breathe, wander = 9 + 2.5 * i, 31 + 6 * i
        dx, dy = (22, 14) if i % 2 == 0 else (-18, 12)
        swell = (f'values="1;1.12;1" keyTimes="0;.5;1" calcMode="spline" keySplines="{ease}" '
                 f'dur="{breathe}s" begin="{-i * 3.1:.1f}s" repeatCount="indefinite"')
        ring_el = (f'<circle r="{r * .78:.0f}" fill="none" stroke="{color}" stroke-width="{max(6, r * .05):.0f}" '
                   f'opacity="{.42 if dark else .8}" filter="url(#{uid}Ring)"/>' if ring else "")
        body.append(
            f'<g transform="translate({cx} {cy})"><g>'
            f'<animateTransform attributeName="transform" type="translate" values="0 0;{dx} {dy};0 0" keyTimes="0;.5;1" '
            f'calcMode="spline" keySplines="{ease}" dur="{wander}s" begin="{-i * 7}s" repeatCount="indefinite"/>'
            f'<g opacity="{core}"><animate attributeName="opacity" values="{core};{core * .6:.2f};{core}" keyTimes="0;.5;1" '
            f'calcMode="spline" keySplines="{ease}" dur="{breathe}s" begin="{-i * 3.1:.1f}s" repeatCount="indefinite"/>'
            f'<g><animateTransform attributeName="transform" type="scale" {swell}/>'
            f'<circle r="{r}" fill="url(#{uid}Glow)"/>{ring_el}</g></g></g></g>')
    return defs, f'<g style="mix-blend-mode:{blend}">{"".join(body)}</g>'
