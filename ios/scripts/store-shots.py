#!/usr/bin/env python3
"""Copies the StoreScreenshots attachments into the App Store folder as JPEG.

    python3 scripts/store-shots.py build/store-shots AppStore/driver/screenshots

The attachment names are the pictures' order ("01-home"); the files are named
iphone69-<name>.jpg, the 6.9" set App Store Connect scales for every iPhone.
"""
import json
import sys
from pathlib import Path

from PIL import Image

source, target = Path(sys.argv[1]), Path(sys.argv[2])
target.mkdir(parents=True, exist_ok=True)
manifest = json.loads((source / "manifest.json").read_text())
for test in manifest:
    for attachment in test.get("attachments", []):
        name = attachment["suggestedHumanReadableName"].split("_")[0]
        image = Image.open(source / attachment["exportedFileName"]).convert("RGB")
        out = target / f"iphone69-{name}.jpg"
        image.save(out, quality=88)
        print(out, image.size)
