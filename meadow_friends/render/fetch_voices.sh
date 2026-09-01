#!/usr/bin/env bash
# fetch_voices.sh - downloads the Piper voice models.
#
# The models are ~200 MB and are not kept in the repository. LibriTTS is the
# one that matters: a single 904-speaker model, which is where all six
# characters get their distinct voices. Both are MIT-licensed releases of the
# Piper project and are free for commercial use.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p voices && cd voices

BASE=https://github.com/rhasspy/piper/releases/download/v0.0.2
for V in en-us-libritts-high en-us-ryan-high; do
  if [ -f "$V.onnx" ]; then
    echo "have $V"
    continue
  fi
  echo "fetching $V ..."
  curl -fL --retry 4 --retry-delay 2 -o "$V.tar.gz" "$BASE/voice-$V.tar.gz"
  tar xzf "$V.tar.gz"
  rm -f "$V.tar.gz" MODEL_CARD
done
ls -la ./*.onnx
