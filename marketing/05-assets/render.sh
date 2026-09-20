#!/usr/bin/env bash
#
# Turns every poster and social HTML in this folder into a PNG.
#
# Run it after editing any HTML (a phone number, an offer line, a link):
#   05-assets/render.sh
#
# A4 posters come out 2480x3508 -- A4 at 300dpi, what a print shop asks for.
# Each poster also gets a _bw copy for a photocopy shop that prints in black
# and white: colour art photocopied without one comes out muddy.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
GRAY="/System/Library/ColorSync/Profiles/Generic Gray Gamma 2.2 Profile.icc"

shot() { # file, width, height, [bw], [scale=2]
  local html="$1" w="$2" h="$3" bw="${4:-}" scale="${5:-2}"
  local png="${html%.html}.png"
  "$CHROME" --headless --disable-gpu --hide-scrollbars \
    --allow-file-access-from-files --force-device-scale-factor="$scale" \
    --virtual-time-budget=4000 --window-size="$w,$h" \
    --screenshot="$png" "file://$html" 2>/dev/null
  echo "  $(basename "$png")  $(sips -g pixelWidth -g pixelHeight "$png" | awk '/pixel/{printf "%s ", $2}')"
  if [ -n "$bw" ]; then
    sips -m "$GRAY" "$png" --out "${html%.html}_bw.png" >/dev/null
    echo "  $(basename "${html%.html}_bw.png")  (for a black-and-white copier)"
  fi
}

echo "posters (A4, 300dpi):"
for f in "$ROOT"/02-posters/*.html; do shot "$f" 1240 1754 bw; done

echo "social:"
for f in "$ROOT"/03-social/*-wide.html;   do [ -e "$f" ] && shot "$f" 1200 630; done
for f in "$ROOT"/03-social/*-square.html; do [ -e "$f" ] && shot "$f" 1080 1080; done

# Profile pictures. Square art (each comes out 2048x2048); every platform crops
# it to a circle, and the mark sits well inside that circle. One file per
# account -- upload the same PNG to Facebook, Instagram, WhatsApp, X, YouTube
# and Telegram; they each downscale it to their own size.
echo "profiles (avatars, cropped to a circle):"
for f in "$ROOT"/03-social/profile-*.html; do [ -e "$f" ] && shot "$f" 1024 1024; done

# Cover / header banners. Each platform wants an exact size and crops
# differently, so these render at their true pixel size (scale 1), not doubled.
# The brand lockup is kept inside every platform's safe area (see cover.css).
echo "covers (each at its exact pixel size):"
[ -e "$ROOT/03-social/cover-fb.html" ]      && shot "$ROOT/03-social/cover-fb.html"      1640 624  "" 1
[ -e "$ROOT/03-social/cover-x.html" ]       && shot "$ROOT/03-social/cover-x.html"       1500 500  "" 1
[ -e "$ROOT/03-social/cover-youtube.html" ] && shot "$ROOT/03-social/cover-youtube.html" 2560 1440 "" 1
echo "done"
