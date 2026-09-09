#!/usr/bin/env bash
# build.sh - rebuilds everything from source.
#
#   ./render/build.sh              full build (voices, audio, subs, video, thumb)
#   ./render/build.sh --quick      540p draft render, for checking staging
#
# The 1080p render takes a couple of hours: WebGL runs on SwiftShader here, and
# reading each frame back out of the GL context costs about a second whatever
# the resolution.
set -euo pipefail
cd "$(dirname "$0")/.."

EP="${1:-ep01}"
case "$EP" in ep*) shift || true ;; *) EP=ep01 ;; esac
OUT=$([ "$EP" = ep01 ] && echo out || echo "out/$EP")
echo "episode: $EP  ->  $OUT"

command -v python3 >/dev/null || { echo "python3 required"; exit 1; }
python3 -c "import piper, numpy" 2>/dev/null || {
  echo "installing python deps"; pip install --quiet piper-tts numpy imageio-ffmpeg; }

[ -f voices/en-us-libritts-high.onnx ] || ./render/fetch_voices.sh

echo "==> speech, music and timeline"
python3 render/make_audio.py --script "episodes/$EP.json" --out "$OUT"

echo "==> subtitles, transcript and description"
python3 render/make_subs.py "$EP"

if [ "${1:-}" = "--quick" ]; then
  echo "==> draft render (960x540)"
  node render/render_video.mjs --ep "$EP" --fps 24 --scale 0.5 --out "$OUT/draft.mp4"
else
  echo "==> render (1920x1080, 24fps)"
  node render/render_video.mjs --ep "$EP" --fps 24 --workers 1 \
    --quality "mat=phong&aa=1&shadow=pcf&smap=1024&seg=20" \
    --out "$OUT/milo-meets-$EP.mp4"
fi

echo "==> thumbnail"
THUMB_EP="$EP" node render/make_thumbnail.mjs

echo
ls -la "$OUT"
