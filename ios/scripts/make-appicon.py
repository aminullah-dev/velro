#!/usr/bin/env python3
"""The iOS app icon, drawn from the Android launcher icon's own geometry.

mobile/app-passenger/src/main/res/drawable/ic_launcher_foreground.xml is the
mark -- a road narrowing to a point, which is also a V -- on a 108-unit
viewport, over ic_launcher_background (#0E6042). Redrawn here rather than
traced by hand, so the two stores show the same icon. Run after changing the
Android mark:

    python3 scripts/make-appicon.py            # the passenger's
    python3 scripts/make-appicon.py --driver   # the driver's
    python3 scripts/make-appicon.py --ops      # the operations console's
    python3 scripts/make-appicon.py --watch    # ...and its Apple Watch app's

The driver's is app-driver's launcher: the same mark on #101828, the road in
the brand's lightest green and the dashes in its darkest, because white on the
dark tile would glare.

The operations console's is the same mark on the brand's one accent, amber,
inside a ring -- the office watching the road -- so nobody opens the console
thinking it is the passenger's app. It runs on the Mac as well, so it also
gets the macOS sizes: the tile inset on Apple's 1024 grid with rounded
corners, since macOS draws an icon as it is rather than masking it.

The watch app's is the console's own tile, full bleed and opaque: watchOS
cuts it to a circle, and the ring sits inside that circle.
"""
import json
import os
import sys

from PIL import Image, ImageDraw

SIZE = 1024
SUPERSAMPLE = 4
VIEWPORT = 108.0
GREEN = (0x0E, 0x60, 0x42)
WHITE = (0xFF, 0xFF, 0xFF)
MINT = (0x8F, 0xD9, 0xBC)
NIGHT = (0x10, 0x18, 0x28)
AMBER = (0xB4, 0x53, 0x09)
CREAM = (0xFE, 0xF3, 0xC7)

DRIVER = "--driver" in sys.argv
WATCH = "--watch" in sys.argv
OPS = "--ops" in sys.argv or WATCH
if WATCH:
    GROUND, ROAD_FILL, DASH_FILL, TARGET = AMBER, WHITE, CREAM, "VelroOpsWatch"
elif OPS:
    GROUND, ROAD_FILL, DASH_FILL, TARGET = AMBER, WHITE, CREAM, "VelroOps"
elif DRIVER:
    GROUND, ROAD_FILL, DASH_FILL, TARGET = NIGHT, MINT, GREEN, "VelroDriver"
else:
    GROUND, ROAD_FILL, DASH_FILL, TARGET = GREEN, WHITE, MINT, "VelroPassenger"

# The Android path data, as polygons in viewport units.
ROAD = [(54, 78), (36, 30), (45, 30), (54, 58), (63, 30), (72, 30)]
DASHES = [
    [(53, 70), (55, 70), (55, 64), (53, 64)],
    [(53, 60), (55, 60), (55, 55), (53, 55)],
    [(53, 51), (55, 51), (55, 47), (53, 47)],
]
# The console's ring, centred on the mark: (centre x, centre y, radius, width).
RING = (54, 54, 36, 2.6)

# macOS: the tile on Apple's grid, and the sizes the asset catalog wants.
MAC_TILE = 824
MAC_RADIUS = 185
MAC_SIZES = [(16, 1), (16, 2), (32, 1), (32, 2), (128, 1), (128, 2), (256, 1), (256, 2), (512, 1), (512, 2)]


def draw_tile(size):
    """The full-bleed square tile, drawn large and scaled down for clean edges."""
    big = size * SUPERSAMPLE
    scale = big / VIEWPORT
    image = Image.new("RGB", (big, big), GROUND)
    draw = ImageDraw.Draw(image)
    if OPS:
        cx, cy, r, w = RING
        draw.ellipse(
            [(cx - r) * scale, (cy - r) * scale, (cx + r) * scale, (cy + r) * scale],
            outline=CREAM, width=int(w * scale),
        )
    draw.polygon([(x * scale, y * scale) for x, y in ROAD], fill=ROAD_FILL)
    for dash in DASHES:
        draw.polygon([(x * scale, y * scale) for x, y in dash], fill=DASH_FILL)
    return image.resize((size, size), Image.LANCZOS)


def mac_master():
    """The tile inset and rounded on a transparent 1024 canvas."""
    tile = draw_tile(MAC_TILE).convert("RGBA")
    mask = Image.new("L", (MAC_TILE * SUPERSAMPLE, MAC_TILE * SUPERSAMPLE), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, MAC_TILE * SUPERSAMPLE - 1, MAC_TILE * SUPERSAMPLE - 1],
        radius=MAC_RADIUS * SUPERSAMPLE, fill=255,
    )
    mask = mask.resize((MAC_TILE, MAC_TILE), Image.LANCZOS)
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    inset = (SIZE - MAC_TILE) // 2
    canvas.paste(tile, (inset, inset), mask)
    return canvas


here = os.path.dirname(os.path.abspath(__file__))
out = os.path.join(here, "..", TARGET, "Resources", "Assets.xcassets", "AppIcon.appiconset")
os.makedirs(out, exist_ok=True)

draw_tile(SIZE).save(os.path.join(out, "AppIcon-1024.png"))
images = [{"filename": "AppIcon-1024.png", "idiom": "universal",
           "platform": "watchos" if WATCH else "ios", "size": "1024x1024"}]

if OPS and not WATCH:
    master = mac_master()
    for points, scale in MAC_SIZES:
        pixels = points * scale
        name = f"AppIcon-mac-{points}@{scale}x.png"
        master.resize((pixels, pixels), Image.LANCZOS).save(os.path.join(out, name))
        images.append({"filename": name, "idiom": "mac", "scale": f"{scale}x", "size": f"{points}x{points}"})

with open(os.path.join(out, "Contents.json"), "w") as f:
    json.dump({"images": images, "info": {"author": "xcode", "version": 1}}, f, indent=2)
with open(os.path.join(out, "..", "Contents.json"), "w") as f:
    json.dump({"info": {"author": "xcode", "version": 1}}, f, indent=2)
print("wrote", os.path.normpath(out))
