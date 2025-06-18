#!/bin/bash
set -e

# Get environment (default to staging if not set)
ENVIRONMENT=${ENVIRONMENT:-staging}

echo "Building frontend for environment: $ENVIRONMENT"

# Clean dist directory
echo "Cleaning dist directory..."
rm -rf dist/*

# Create dist directory if it doesn't exist
mkdir -p dist

# Set API URL based on environment
# Note: These URLs should be updated with actual deployed API Gateway URLs
case $ENVIRONMENT in
  production)
    API_BASE_URL="https://b3q0v6btng.execute-api.eu-north-1.amazonaws.com/prod"
    ;;
  staging)
    # This is a placeholder - should be updated with actual staging API Gateway URL
    # The actual URL will be available after first staging deployment
    API_BASE_URL="https://api.staging.atwood-sniper.com"
    ;;
  *)
    echo "Unknown environment: $ENVIRONMENT"
    echo "Defaulting to staging API"
    API_BASE_URL="https://api.staging.atwood-sniper.com"
    ;;
esac

echo "Using API URL: $API_BASE_URL"

# Create a copy of Config.elm with the correct API URL
cp src/Config.elm src/Config.elm.backup
sed "s|API_BASE_URL_PLACEHOLDER|$API_BASE_URL|g" src/Config.elm.backup > src/Config.elm

# Generate Elm Tailwind modules
npx elm-tailwind-modules --dir src

# Compile Elm code
npx --yes elm make src/Main.elm --output=dist/elm.js --optimize

# Copy public files to dist
cp -r public/* dist/

# Replace API URL in index.html as well
sed "s|https://b3q0v6btng.execute-api.eu-north-1.amazonaws.com/prod|$API_BASE_URL|g" dist/index.html > dist/index.html.tmp
mv dist/index.html.tmp dist/index.html

# Build Tailwind CSS
npm run build

# Restore original Config.elm
mv src/Config.elm.backup src/Config.elm

echo "Build complete! Output is in dist/"
echo "API URL configured: $API_BASE_URL"
