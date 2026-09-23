#!/usr/bin/env python3
"""Prepare the crops that gen_hero.py embeds into the banners.

Inputs (not tracked, at the repo root): the "文学少女" illustrations
    012.jpg (4961x3502) - the girl waving from behind the classroom window
    001.jpg (1600x1130) - the girl sitting in fallen maple leaves
    022.jpg (4976x3502) - the girl reaching up to the window (right page only; the book on the left page is dropped)
    021.jpg (4966x3502) - the girl holding a red book under the golden tree
Outputs: scripts/hero.jpg, scripts/footer.jpg, scripts/stats.jpg, scripts/works.jpg (the last two are embedded by
gen_cards.py)
Needs Pillow (pip install Pillow; CI never runs this, so it is not in requirements.txt).
Run only when the source art changes:
    python scripts/prep_images.py [dir-with-sources]
"""
import os
import sys

from PIL import Image, ImageEnhance

HERE = os.path.dirname(os.path.abspath(__file__))

# name: (source, crop box in source pixels, output size)
CROPS = {
    # head to hand, cut right after the panel she hides behind; aspect matches the 560x480 slot
    "hero": ("012.jpg", (0, 120, 2484, 2250), (1008, 864)),
    # her and both braids, stopping short of the vertical poem on the right; aspect matches the 485x380 slot
    "footer": ("001.jpg", (0, 20, 1200, 960), (970, 760)),
    # head to waist with the raised hand and the pink book; aspect matches the 524x480 slot of the stats panel
    "stats": ("022.jpg", (2300, 100, 4700, 2300), (1048, 960)),
    # head to skirt with the red book held to her chest and the braid swinging out, clear of the vertical passage on
    # her left and the folio at the foot; aspect matches the 620x728 slot of the works-in-progress card
    "works": ("021.jpg", (819, 298, 3054, 2922), (930, 1092)),
}


def main(src_dir="."):
    for name, (src, box, size) in CROPS.items():
        crop = Image.open(os.path.join(src_dir, src)).convert("RGB").crop(box)
        # the scans are slightly washed out; a touch of contrast keeps linework readable once scaled down
        crop = ImageEnhance.Contrast(crop).enhance(1.06)
        out = crop.resize(size, Image.LANCZOS)
        path = os.path.join(HERE, f"{name}.jpg")
        out.save(path, "JPEG", quality=84, optimize=True, subsampling=1)
        print(f"{path}: {os.path.getsize(path)//1024} KB")


if __name__ == "__main__":
    main(*sys.argv[1:])
