#!/bin/bash
set -e

# Clean dist directory
echo "Cleaning dist directory..."
rm -rf dist/*

# Create dist directory if it doesn't exist
mkdir -p dist

# Generate Elm Tailwind modules
npx elm-tailwind-modules --dir src

# Compile Elm code
npx --yes elm make src/Main.elm --output=dist/elm.js --optimize

# Copy public files to dist
cp -r public/* dist/

# Build Tailwind CSS
#npx --yes tailwindcss -o dist/tailwind.css --minify
npm run build

# Update index.html to use the compiled elm.js
# sed -i '' 's/<script src="elm.js"><\/script>/<script src="elm.js"><\/script>\n<script>\n  var app = Elm.Main.init({ node: document.getElementById("elm") });\n<\/script>/' dist/index.html

echo "Build complete! Output is in dist/"
