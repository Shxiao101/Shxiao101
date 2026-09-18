"""The maple leaf shared by the footer's falling leaves (gen_hero.py) and the bookshelf's vase (gen_cards.py).

A Japanese maple (Acer palmatum), built once at import: seven lance-shaped lobes fanned out from a small palm,
each drawn out to a long point, with serrated edges whose teeth lean toward the lobe tips; a thin stalk; veins
running from the stalk out to every tip; and a tint that warms the middle and deepens the tips, so one fill
colour (set by the <use>) reads as a real leaf.  Centred on the origin, ~17 units across, stalk pointing down.
Standard library only.
"""
import math

# (degrees clockwise from straight up, length): the middle lobe longest, the pair beside the stalk short,
# left and right a little uneven, as on a real leaf
LOBES = [(0, 11.2), (36, 10.5), (-37, 10.8), (72, 9.0), (-71, 9.3), (119, 5.6), (-117, 5.9)]
PALM = 2.2                    # radius of the solid middle: how deep the notches between the lobes cut
WIDTH = .19                   # a lobe's half-width at its widest, as a fraction of its length
TAPER = (.85, 1.25)           # lobe profile t^a (1-t)^b: narrow at the palm, widest ~40% out, then a long point
TOOTH, BITE = .72, .2         # serration: spacing along the edge and depth, in leaf units
LEAF_COLORS = ["#e8430a", "#f47e08", "#d03906", "#c21d0a", "#f7970b", "#faae13", "#e86108"]   # sampled from 001.jpg

_A, _B = TAPER
_PEAK = (_A / (_A + _B)) ** _A * (_B / (_A + _B)) ** _B


def _half_width(t, length):
    return WIDTH * length * t ** _A * (1 - t) ** _B / _PEAK


def _reach(delta, length):
    """How far a ray at `delta` radians off a lobe's axis runs inside that lobe.  Each lobe is star-shaped about
    the leaf's centre (its half-width over its distance out only falls), so this is one crossing, found by halving."""
    if abs(delta) >= math.pi / 2:
        return 0.0
    slope = math.tan(abs(delta))
    lo, hi = 0.0, 1.0
    for _ in range(30):
        t = (lo + hi) / 2
        if t > 0 and _half_width(t, length) / (t * length) >= slope:
            lo = t
        else:
            hi = t
    return lo * length / math.cos(delta)


def _outline(steps=1800):
    """Smooth outline, clockwise from the top: at each angle the farthest of the palm and the lobes."""
    pts = []
    for i in range(steps):
        th = 2 * math.pi * i / steps
        r = PALM
        for ang, length in LOBES:
            d = (th - math.radians(ang) + math.pi) % (2 * math.pi) - math.pi
            r = max(r, _reach(d, length))
        pts.append((r * math.sin(th), -r * math.cos(th)))
    return pts


def _resample(pts, ds):
    """Evenly spaced points along the closed outline."""
    out, carry = [pts[0]], 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        seg = math.hypot(x1 - x0, y1 - y0)
        pos = ds - carry
        while pos <= seg:
            out.append((x0 + (x1 - x0) * pos / seg, y0 + (y1 - y0) * pos / seg))
            pos += ds
        carry = seg - (pos - ds)
    return out[:-1]


def _serrate(pts, ds):
    """Cut teeth into the edge.  Walking out toward a tip each tooth rises gently and drops steeply, walking back in
    it is the mirror image, so every tooth leans toward the tip of its lobe.  None deep in the notches."""
    n = len(pts)
    out = []
    for k, (x, y) in enumerate(pts):
        (xa, ya), (xb, yb) = pts[k - 1], pts[(k + 1) % n]
        tx, ty = xb - xa, yb - ya
        tl = math.hypot(tx, ty) or 1
        nx, ny = -ty / tl, tx / tl                       # outward for a clockwise (on screen) outline
        r = math.hypot(x, y)
        outward = math.hypot(xb, yb) > math.hypot(xa, ya)
        ph = (k * ds / TOOTH) % 1
        if not outward:
            ph = 1 - ph
        depth = 1 - ph / .65 if ph < .65 else (ph - .65) / .35
        th = math.degrees(math.atan2(x, -y))
        length = min(LOBES, key=lambda lb: abs((th - lb[0] + 180) % 360 - 180))[1]
        fade = min(1, max(0, (r - PALM * 1.3) / 1.4), max(0, (length * .94 - r) / (length * .1)))
        fade = fade * fade * (3 - 2 * fade)
        out.append((x - nx * BITE * depth * fade, y - ny * BITE * depth * fade))
    return out


def _simplify(pts, tol):
    """Ramer-Douglas-Peucker on a closed outline: drop points that sit within `tol` of the line past them."""
    keep = [False] * len(pts)
    keep[0] = keep[len(pts) // 2] = True
    stack = [(0, len(pts) // 2), (len(pts) // 2, len(pts))]
    while stack:
        i, j = stack.pop()
        (x0, y0), (x1, y1) = pts[i], pts[j % len(pts)]
        dx, dy = x1 - x0, y1 - y0
        dl = math.hypot(dx, dy) or 1
        far, idx = 0.0, None
        for k in range(i + 1, j):
            d = abs((pts[k][0] - x0) * dy - (pts[k][1] - y0) * dx) / dl
            if d > far:
                far, idx = d, k
        if idx is not None and far > tol:
            keep[idx] = True
            stack += [(i, idx), (idx, j)]
    return [p for p, kept in zip(pts, keep) if kept]


def _path(pts):
    return "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts) + " Z"


def _veins():
    """Main veins from the stalk to each tip, bowed slightly; fine side veins branching off toward the edges."""
    main, side = [], []
    for i, (ang, length) in enumerate(LOBES):
        a = math.radians(ang)
        ux, uy, px, py = math.sin(a), -math.cos(a), math.cos(a), math.sin(a)
        bend = .04 * length * (1 if i % 2 else -1)
        tip = .93 * length
        main.append(f"M0,0 Q{ux * tip / 2 + px * bend:.2f},{uy * tip / 2 + py * bend:.2f} {ux * tip:.2f},{uy * tip:.2f}")
        for t in (.3, .46, .62, .78):
            u, reach = t * length, _half_width(t, length) * .8
            bx, by = ux * u + px * bend * 4 * t * (1 - t), uy * u + py * bend * 4 * t * (1 - t)
            for s in (-1, 1):   # 45 degrees off the midrib, toward the tip
                ex, ey = bx + (ux + s * px) * reach * .72, by + (uy + s * py) * reach * .72
                side.append(f"M{bx:.2f},{by:.2f} L{ex:.2f},{ey:.2f}")
    return " ".join(main), " ".join(side)


BLADE = _path(_simplify(_serrate(_resample(_outline(), .05), .05), .02))
MAIN_VEINS, SIDE_VEINS = _veins()
STALK = "M-.36,0 Q-.1,4.6 .68,9.2 L1.06,9.05 Q.36,4.5 .36,0 Z"
STALK_END = (.87, 9.12)       # the stalk's cut end, where a leaf hangs from its twig


def leaf_def(id_="leaf"):
    """The leaf's tint gradient and the leaf itself, for <defs>; the <use> sets its fill colour."""
    return (f'<radialGradient id="{id_}Tint" gradientUnits="userSpaceOnUse" cx="0" cy="0" r="11.8">'
            f'<stop offset="0" stop-color="#fff0a0" stop-opacity=".55"/><stop offset=".3" stop-color="#ffc45a" stop-opacity=".2"/>'
            f'<stop offset=".62" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#2a0000" stop-opacity=".3"/>'
            f'</radialGradient>'
            f'<g id="{id_}" stroke="none"><path d="{STALK}"/><path d="{BLADE}"/><path d="{BLADE}" fill="url(#{id_}Tint)"/>'
            f'<path d="{MAIN_VEINS}" fill="none" stroke="#ffe7b8" stroke-opacity=".38" stroke-width=".22" stroke-linecap="round"/>'
            f'<path d="{SIDE_VEINS}" fill="none" stroke="#ffe7b8" stroke-opacity=".22" stroke-width=".12" stroke-linecap="round"/></g>')
