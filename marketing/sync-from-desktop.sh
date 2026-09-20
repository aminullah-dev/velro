#!/usr/bin/env bash
#
# The marketing folder is worked on at ~/Desktop/Marketing/Velro, which is not
# in git -- it was lost once already. This copies the sources back here so a
# commit keeps them.
#
#   marketing/sync-from-desktop.sh && git add marketing && git commit
#
# PNGs and the copied store listings are left behind on purpose: render.sh
# rebuilds the first, and the second already lives in this repository.
set -euo pipefail
DESK="${VELRO_MARKETING:-$HOME/Desktop/Marketing/Velro}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -d "$DESK" ] || { echo "not found: $DESK -- set VELRO_MARKETING"; exit 1; }
rsync -a --delete \
  --exclude "*.png" --exclude ".DS_Store" \
  --exclude "04-store-listings/google-play/" --exclude "04-store-listings/app-store/" \
  "$DESK/" "$HERE/"
git -C "$HERE/.." status --short marketing
