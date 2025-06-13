#!/bin/bash

# set -e

# Constants
LAYER_DIR="layer"
OUT_DIR="out"
PYTHON_VERSION="3.11"
DOCKER_IMAGE="amazonlinux:2023"
REQUIREMENTS="requirements.txt"

# Ensure output and working directories exist
mkdir -p "$LAYER_DIR/python"
mkdir -p "$OUT_DIR"

echo "🛠️ Building Lambda layer in Docker..."

cp $LAYER_DIR/$REQUIREMENTS $PWD


docker run -it --rm \
  -v "$PWD":/var/task \
  amazonlinux:2023 \
  bash -c "
    cd /var/task && \
    yum install -y python3 python3-pip zip python3-setuptools && \
    mkdir -p out/layer/python && \
    pip3 install --no-cache-dir --target out/layer/python beautifulsoup4 requests && \
    pip3 install --no-cache-dir --target out/layer/python -r /var/task/requirements.txt && \
    cd out/layer && zip -r ../layer.zip python"

rm $REQUIREMENTS

echo "✅ Layer build complete: $OUT_DIR/layer.zip"
