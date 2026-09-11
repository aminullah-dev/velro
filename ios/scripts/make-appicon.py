#!/usr/bin/env python3
"""The iOS app icon, drawn from the Android launcher icon's own geometry.

mobile/app-passenger/src/main/res/drawable/ic_launcher_foreground.xml is the
mark -- a road narrowing to a point, which is also a V -- on a 108-unit
viewport, over ic_launcher_background (#0E6042). Redrawn here rather than
traced by hand, so the two stores show the same icon. Run after changing the
Android mark:

    python3 scripts/make-appicon.py            # the passenger's
    python3 scripts/make-appicon.py --driver   # the driver's

The driver's is app-driver's launcher: the same mark on #101828, the road in
the brand's lightest green and the dashes in its darkest, because white on the
dark tile would glare.
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

DRIVER = "--driver" in sys.argv
GROUND, ROAD_FILL, DASH_FILL, TARGET = (
    (NIGHT, MINT, GREEN, "VelroDriver") if DRIVER else (GREEN, WHITE, MINT, "VelroPassenger")
)

# The Android path data, as polygons in viewport units.
ROAD = [(54, 78), (36, 30), (45, 30), (54, 58), (63, 30), (72, 30)]
DASHES = [
    [(53, 70), (55, 70), (55, 64), (53, 64)],
    [(53, 60), (55, 60), (55, 55), (53, 55)],
    [(53, 51), (55, 51), (55, 47), (53, 47)],
]

here = os.path.dirname(os.path.abspath(__file__))
out = os.path.join(here, "..", TARGET, "Resources", "Assets.xcassets", "AppIcon.appiconset")
os.makedirs(out, exist_ok=True)

big = SIZE * SUPERSAMPLE
scale = big / VIEWPORT
image = Image.new("RGB", (big, big), GROUND)
draw = ImageDraw.Draw(image)
draw.polygon([(x * scale, y * scale) for x, y in ROAD], fill=ROAD_FILL)
for dash in DASHES:
    draw.polygon([(x * scale, y * scale) for x, y in dash], fill=DASH_FILL)
image.resize((SIZE, SIZE), Image.LANCZOS).save(os.path.join(out, "AppIcon-1024.png"))

with open(os.path.join(out, "Contents.json"), "w") as f:
    json.dump({
        "images": [{"filename": "AppIcon-1024.png", "idiom": "universal", "platform": "ios", "size": "1024x1024"}],
        "info": {"author": "xcode", "version": 1},
    }, f, indent=2)
with open(os.path.join(out, "..", "Contents.json"), "w") as f:
    json.dump({"info": {"author": "xcode", "version": 1}}, f, indent=2)
print("wrote", os.path.normpath(out))
