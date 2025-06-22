#!/usr/bin/env bash
set -euo pipefail

HOOKS_DIR="$(git rev-parse --git-dir)/hooks"
mkdir -p "$HOOKS_DIR"

for hook in scripts/git-hooks/*; do
    name=$(basename "$hook")
    cp "$hook" "$HOOKS_DIR/$name"
    chmod +x "$HOOKS_DIR/$name"
done

echo "Git hooks installed to $HOOKS_DIR"
