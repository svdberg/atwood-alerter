#!/bin/bash

set -e

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

docker run --rm -v "$PWD":/var/task $DOCKER_IMAGE bash -c "
  cd /var/task && yum install -y python${PYTHON_VERSION} python${PYTHON_VERSION}-pip zip > /dev/null &&
  python${PYTHON_VERSION} -m pip install -r $REQUIREMENTS -t $LAYER_DIR/python &&
  cd $LAYER_DIR && zip -r ../$OUT_DIR/layer.zip python > /dev/null
"
rm $REQUIREMENTS

echo "✅ Layer build complete: $OUT_DIR/layer.zip"
