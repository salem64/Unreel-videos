#!/usr/bin/env bash
# Installs the free voice engine and downloads the voice model (not stored in git, too large).
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
pip install --break-system-packages -q kokoro-onnx soundfile pillow numpy
mkdir -p "$DIR/models"
[ -f "$DIR/models/kokoro.onnx" ] || curl -sSL -o "$DIR/models/kokoro.onnx" https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.int8.onnx
[ -f "$DIR/models/voices.bin" ] || curl -sSL -o "$DIR/models/voices.bin" https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
echo "setup ok"
