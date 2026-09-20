#!/usr/bin/env bash
#
# The store listings live in the repository -- that is where the upload
# scripts read them, so that copy is the one that is true. This pulls a copy
# here for when you are writing an advertisement and want the same words and
# the same screenshots in front of you.
#
# Edit the repository's copy, then run this. Never the other way round.
#
# The review demo videos (~60MB) and the signed AABs are deliberately left
# behind: they belong to a store submission, not to marketing.
set -euo pipefail
REPO="${VELRO_REPO:-$HOME/Velro}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -d "$REPO" ] || { echo "repository not found at $REPO -- set VELRO_REPO"; exit 1; }

rsync -a --delete \
  --exclude "build/" --exclude "*.mp4" --exclude ".DS_Store" \
  "$REPO/mobile/PlayStore/" "$HERE/google-play/"
rsync -a --delete \
  --exclude "build/" --exclude "*.mp4" --exclude ".DS_Store" \
  "$REPO/ios/AppStore/" "$HERE/app-store/"

echo "copied from $REPO:"
du -sh "$HERE/google-play" "$HERE/app-store"
