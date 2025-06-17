#!/bin/bash

set -e  # Exit on error

# Constants
LAYER_DIR="layer"
OUT_DIR="out"
DOCKER_IMAGE="amazonlinux:2023"
REQUIREMENTS="requirements.txt"

# Ensure output and working directories exist
mkdir -p "$LAYER_DIR/python"
mkdir -p "$OUT_DIR"

echo "🛠️ Building Lambda layer in Docker..."

cp "$LAYER_DIR/$REQUIREMENTS" "$PWD"


docker run --rm \
  -v "$PWD":/var/task \
  "$DOCKER_IMAGE" \
  bash -c "
    cd /var/task && \
    yum install -y python3 python3-pip zip python3-setuptools && \
    mkdir -p ${OUT_DIR}/${LAYER_DIR}/python && \
    pip3 install --no-cache-dir --target ${OUT_DIR}/${LAYER_DIR}/python beautifulsoup4 requests && \
    pip3 install --no-cache-dir --target ${OUT_DIR}/${LAYER_DIR}/python -r /var/task/${REQUIREMENTS} && \
    cd ${OUT_DIR}/${LAYER_DIR} && zip -r ../layer.zip python"

rm "$REQUIREMENTS"

# Verify the layer was created successfully
if [ -f "$OUT_DIR/layer.zip" ]; then
    echo "✅ Layer build complete: $OUT_DIR/layer.zip"
    echo "📦 Layer size: $(du -h $OUT_DIR/layer.zip | cut -f1)"
    echo "📁 Contents preview:"
    unzip -l "$OUT_DIR/layer.zip" | head -10
else
    echo "❌ Error: Layer build failed - $OUT_DIR/layer.zip not found"
    exit 1
fi
