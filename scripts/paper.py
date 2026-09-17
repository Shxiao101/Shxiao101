"""Binder punch holes down the left edge of a card, like the loose-leaf page in 065.jpg.

The holes are real cut-outs (an even-odd clip over the whole card), so the GitHub page shows through them.
A clip rather than a mask: it is plain geometry, so the animated cards get no extra luminance layer to composite.
Every card uses the same radius, pitch and inset, so stacked cards line up like pages in a binder.
Standard library only; imported by gen_hero.py and gen_cards.py.
"""
import re

R = 8            # hole radius
PITCH = 40       # centre-to-centre spacing
CX = 26          # inset from the punched edge
MARGIN = 36      # keep clear of the rounded corners


def hole_ys(h):
    n = int((h - 2 * MARGIN) // PITCH) + 1
    y0 = (h - (n - 1) * PITCH) / 2
    return [y0 + i * PITCH for i in range(n)]


def punch(svg, dark, side="left"):
    """Cut the holes into a finished card svg and shade the top rim of each one, as on the scan.
    `side` is the edge away from the card's character art."""
    _, _, w, h = map(float, re.search(r'viewBox="([^"]+)"', svg).group(1).split())
    head = svg.index(">", svg.index("<svg")) + 1
    tail = svg.rindex("</svg>")
    ys = hole_ys(h)
    cx = CX if side == "left" else w - CX
    cuts = "".join(f"M{cx-R:.0f},{y:.0f} a{R},{R} 0 1 0 {2*R},0 a{R},{R} 0 1 0 {-2*R},0 Z " for y in ys)

    def crescent(angle):
        # between the upper half of the hole and a flatter half-ellipse, turned to face `angle`
        return "".join(
            f'<path transform="rotate({angle} {cx:.0f} {y:.0f})" d="M{cx-R:.0f},{y:.0f} A{R},{R} 0 0 1 {cx+R:.0f},{y:.0f} '
            f'A{R},{R*.58:.1f} 0 0 0 {cx-R:.0f},{y:.0f} Z"/>' for y in ys)

    shade = f'<g fill="#000" opacity="{".45" if dark else ".24"}">{crescent(-25)}</g>'
    if dark:
        # the page behind is as dark as the card, so light the cut instead: a thin rim on the paper
        # and the lower inner wall catching the same top-left light that casts the shadow
        ring = "".join(f'<circle cx="{cx:.0f}" cy="{y:.0f}" r="{R + .6}"/>' for y in ys)
        shade += (f'<g fill="none" stroke="#fff3c4" stroke-opacity=".30" stroke-width="1.2">{ring}</g>'
                  f'<g fill="#fff3c4" opacity=".22">{crescent(155)}</g>')
    return (svg[:head]
            + f'<defs><clipPath id="punch"><path clip-rule="evenodd" d="M0,0 H{w:.0f} V{h:.0f} H0 Z {cuts}"/></clipPath></defs>'
            + f'<g clip-path="url(#punch)">{svg[head:tail]}</g>'
            + shade
            + svg[tail:])
