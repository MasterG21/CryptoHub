#!/usr/bin/env bash
# build.sh - rebuilds every output from source.
#
#   ./render/build.sh            full build (audio, subs, video, thumbnail)
#   ./render/build.sh --quick    half-size, no-audio-rebuild preview render
#
# Outputs land in out/ .
set -euo pipefail
cd "$(dirname "$0")/.."

FFMPEG=$(python3 -c "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())" 2>/dev/null \
         || command -v ffmpeg)
[ -x "$FFMPEG" ] || { echo "no ffmpeg found (pip install imageio-ffmpeg)"; exit 1; }
echo "ffmpeg: $FFMPEG"

echo "==> regenerating web/script-data.js from script.json"
python3 - <<'PY'
data = open('script.json').read().rstrip()
open('web/script-data.js', 'w').write(
    '/* Generated from ../script.json by render/build.sh - do not edit. */\n'
    'window.SCRIPT = ' + data + ';\n')
PY

if command -v pyftsubset >/dev/null 2>&1; then
  echo "==> regenerating web/fonts.css from assets/fonts"
  python3 render/make_fonts.py
else
  echo "==> pyftsubset not installed, keeping the committed web/fonts.css"
fi

echo "==> soundtrack"
python3 render/make_audio.py

echo "==> subtitles, lyrics and description"
python3 render/make_subs.py

if [ "${1:-}" = "--quick" ]; then
  echo "==> preview render (960x540)"
  node render/render_video.mjs --scale 0.5 --format jpeg --out out/preview.mp4
else
  echo "==> video render (1920x1080)"
  node render/render_video.mjs
fi

echo "==> thumbnail"
node render/make_thumbnail.mjs

echo
echo "done. files in out/:"
ls -la out/
