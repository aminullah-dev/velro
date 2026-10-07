#!/usr/bin/env bash
#
# Renders teaser-ghorband.html into an MP4. The scene draws one deterministic
# frame per Chrome screenshot (the frame index is passed in the URL hash), so
# frames render in parallel and the result is byte-identical every run. ffmpeg
# then stitches them. Needs ffmpeg (brew install ffmpeg).
#
#   06-video/render-video.sh            # 144 frames @ 24fps = 6s, 1080x1920
#   06-video/render-video.sh 180 30     # frames, fps
#
# The loop is seamless: play it as a looping reel and it never jumps.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
FFMPEG="$(command -v ffmpeg || echo /opt/homebrew/bin/ffmpeg)"
SCENE="$HERE/teaser-ghorband.html"
N="${1:-144}"; FPS="${2:-24}"; W=1080; H=1920
FR="$HERE/frames"; OUT="$HERE/teaser-ghorband.mp4"
rm -rf "$FR"; mkdir -p "$FR"

echo "rendering $N frames (${W}x${H}) ..."
seq 0 $((N - 1)) | xargs -P 6 -I {} "$CHROME" --headless --disable-gpu --hide-scrollbars \
  --allow-file-access-from-files --force-device-scale-factor=1 --virtual-time-budget=1800 \
  --window-size="$W,$H" --screenshot="$FR/f{}.png" "file://$SCENE#f={}&N=$N" 2>/dev/null
echo "  got $(ls "$FR"/f*.png | wc -l | tr -d ' ')/$N frames"

echo "encoding ..."
"$FFMPEG" -y -framerate "$FPS" -start_number 0 -i "$FR/f%d.png" \
  -c:v libx264 -pix_fmt yuv420p -crf 20 -movflags +faststart "$OUT" 2>/dev/null
rm -rf "$FR"
echo "done: $OUT  ($(du -h "$OUT" | cut -f1))"
