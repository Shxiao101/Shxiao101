"""The maple leaf shared by the footer's falling leaves (gen_hero.py) and the bookshelf's vase (gen_cards.py).
Standard library only.
"""

# Stylised five-lobed maple leaf centred on the origin, ~19 units across, stem pointing down.
LEAF = ("M0,-10 L1.5,-6.5 L3.2,-7.2 L2.6,-3.6 L6.8,-5.2 L6,-3.2 L9.2,-2.4 L6.4,.4 L7.2,1.8 L3.4,2 L3.8,4.2 "
        "L.8,3 L.6,7 L-.6,7 L-.8,3 L-3.8,4.2 L-3.4,2 L-7.2,1.8 L-6.4,.4 L-9.2,-2.4 L-6,-3.2 L-6.8,-5.2 "
        "L-2.6,-3.6 L-3.2,-7.2 L-1.5,-6.5 Z")
VEINS = "M0,5 V-7.5 M0,1.5 L6.2,-3.6 M0,1.5 L-6.2,-3.6 M0,3 L5.4,1.4 M0,3 L-5.4,1.4"
LEAF_COLORS = ["#e8430a", "#f47e08", "#d03906", "#c21d0a", "#f7970b", "#faae13", "#e86108"]   # sampled from 001.jpg


def leaf_def(id_="leaf"):
    """A <g> for <defs>: the leaf with its veins, filled by whatever uses it."""
    return (f'<g id="{id_}"><path d="{LEAF}"/><path d="{VEINS}" fill="none" stroke="#4a1400" stroke-opacity=".35" '
            f'stroke-width=".45" stroke-linecap="round"/></g>')
