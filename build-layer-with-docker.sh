#!/bin/bash

# set -e

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


docker run -it --rm \
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

echo "✅ Layer build complete: $OUT_DIR/layer.zip"
