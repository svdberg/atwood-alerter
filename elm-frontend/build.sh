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

# Dynamically get API URL from CloudFormation stack outputs
# Set stack name based on environment
case $ENVIRONMENT in
  production)
    STACK_NAME="AtwoodMonitor-Production-Main"
    ;;
  staging)
    STACK_NAME="AtwoodMonitor-Staging-Main"
    ;;
  *)
    echo "Unknown environment: $ENVIRONMENT"
    echo "Defaulting to staging"
    STACK_NAME="AtwoodMonitor-Staging-Main"
    ;;
esac

echo "Fetching API Gateway URL from CloudFormation stack: $STACK_NAME"

# Set the correct region based on environment
case $ENVIRONMENT in
  production)
    AWS_REGION="eu-north-1"
    ;;
  staging)
    AWS_REGION="us-west-2"
    ;;
  *)
    echo "Unknown environment: $ENVIRONMENT"
    echo "Defaulting to staging"
    AWS_REGION="us-west-2"
    STACK_NAME="AtwoodMonitor-Staging-Main"
    ;;
esac

# Get API Gateway URL from environment variable (CI/CD) or CloudFormation stack outputs
if [ -n "$API_BASE_URL" ]; then
  echo "Using API URL from environment variable: $API_BASE_URL"
else
  # Check if AWS CLI is available and configured
  if command -v aws >/dev/null 2>&1 && aws sts get-caller-identity >/dev/null 2>&1; then
    echo "Fetching API Gateway URL from CloudFormation stack: $STACK_NAME"
    API_BASE_URL=$(aws cloudformation describe-stacks \
      --stack-name "$STACK_NAME" \
      --region "$AWS_REGION" \
      --query "Stacks[0].Outputs[?OutputKey=='ApiEndpoint'].OutputValue" \
      --output text 2>/dev/null)
  else
    echo "AWS CLI not available or not configured. Using placeholder URL for CI/CD builds."
    API_BASE_URL=""
  fi
fi

if [ -z "$API_BASE_URL" ] || [ "$API_BASE_URL" = "None" ]; then
  echo "Warning: Could not fetch API Gateway URL from stack $STACK_NAME"
  echo "Using placeholder URL for CI/CD builds."
  
  # Use placeholder URLs for CI/CD builds when stack doesn't exist yet or AWS not available
  case $ENVIRONMENT in
    production)
      API_BASE_URL="https://placeholder-prod-api.execute-api.eu-north-1.amazonaws.com/prod"
      ;;
    staging)
      API_BASE_URL="https://placeholder-staging-api.execute-api.us-west-2.amazonaws.com/prod"
      ;;
    *)
      API_BASE_URL="https://placeholder-staging-api.execute-api.us-west-2.amazonaws.com/prod"
      ;;
  esac
  
  echo "Using placeholder API URL for initial build: $API_BASE_URL"
  echo "This will be updated after deployment when the real API URL is available."
fi

# VAPID public key for web push. It must belong to the same key pair the
# environment's push Lambda signs with (SSM /atwood/staging/vapid_private_key
# on staging, /atwood/vapid_private_key on production), or push services
# reject every message (Apple: "VapidPkHashMismatch").
# Order: $VAPID_PUBLIC_KEY env var, then the environment's SSM parameter.
PRODUCTION_VAPID_PUBLIC_KEY="BEnxJVSWp29XBixAH33uFwYsKxYjDkiXbswbDDWwvCS-Lkx09lXCPSxS55cNPk6tRQDF2uzpJbYFzMeSyKxVRYk"
case $ENVIRONMENT in
  production) VAPID_PARAM="/atwood/vapid_public_key" ;;
  *)          VAPID_PARAM="/atwood/staging/vapid_public_key" ;;
esac
if [ -z "$VAPID_PUBLIC_KEY" ] && command -v aws >/dev/null 2>&1 && aws sts get-caller-identity >/dev/null 2>&1; then
  # --with-decryption: the parameter may be a SecureString (production's is).
  # Without it SSM returns KMS ciphertext ("AQICAH…") instead of the key.
  VAPID_PUBLIC_KEY=$(aws ssm get-parameter --name "$VAPID_PARAM" --region "$AWS_REGION" \
    --with-decryption --query "Parameter.Value" --output text 2>/dev/null | tr -d '[:space:]') || VAPID_PUBLIC_KEY=""
fi
# A VAPID public key is an uncompressed P-256 point: 65 bytes, base64url
# without padding = 87 characters, starting with "B". Anything else (e.g.
# ciphertext, a private key, a typo) would silently break push.
if [ -n "$VAPID_PUBLIC_KEY" ] && [ "$VAPID_PUBLIC_KEY" != "None" ] \
   && ! [[ "$VAPID_PUBLIC_KEY" =~ ^B[A-Za-z0-9_-]{86}$ ]]; then
  echo "::error::VAPID public key for $ENVIRONMENT (from ${VAPID_PARAM} or \$VAPID_PUBLIC_KEY) is not a valid base64url P-256 public key: ${VAPID_PUBLIC_KEY:0:12}…"
  exit 1
fi
if [ -z "$VAPID_PUBLIC_KEY" ] || [ "$VAPID_PUBLIC_KEY" = "None" ]; then
  if [ "$ENVIRONMENT" = "production" ]; then
    # Long-standing production key; keeps existing production subscribers working.
    VAPID_PUBLIC_KEY="$PRODUCTION_VAPID_PUBLIC_KEY"
    echo "VAPID public key: SSM $VAPID_PARAM unavailable, using the built-in production key"
  else
    VAPID_PUBLIC_KEY="VAPID_PUBLIC_KEY_UNSET"
    echo "Warning: no VAPID public key for $ENVIRONMENT; push notifications will be disabled in this build"
  fi
else
  echo "VAPID public key for $ENVIRONMENT: ${VAPID_PUBLIC_KEY:0:12}… (from ${VAPID_PARAM})"
  if [ "$ENVIRONMENT" = "production" ] && [ "$VAPID_PUBLIC_KEY" != "$PRODUCTION_VAPID_PUBLIC_KEY" ]; then
    echo "::warning::Production VAPID public key in SSM differs from the long-standing key; existing subscribers will be re-subscribed on their next visit"
  fi
fi

# Remove trailing slash from API_BASE_URL to avoid double slashes
API_BASE_URL=$(echo "$API_BASE_URL" | sed 's:/*$::')

echo "Using API URL: $API_BASE_URL"

# Generate Config.elm from template with the correct API URL.
# Always restore the committed version on exit (including on failure), so a
# broken build never leaves an environment-specific Config.elm in the tree.
restore_config() {
  cp src/Config.elm.template src/Config.elm
}
trap restore_config EXIT
sed "s|API_BASE_URL_PLACEHOLDER|$API_BASE_URL|g" src/Config.elm.template > src/Config.elm

# Generate Elm Tailwind modules
npx elm-tailwind-modules --dir src

# Compile Elm code
npx --yes elm make src/Main.elm --output=dist/elm.js --optimize
mkdir -p dist/admin
npx --yes elm make src/Admin.elm --output=dist/admin/admin.js --optimize

# Copy public files to dist
cp -r public/* dist/
mkdir -p dist/admin
cp admin/index.html dist/admin/
# Replace API URL in admin/index.html (portable across macOS and Linux)
cat dist/admin/index.html | sed "s|API_BASE_URL_PLACEHOLDER|$API_BASE_URL|g" > dist/admin/index.html.tmp
mv dist/admin/index.html.tmp dist/admin/index.html

# Replace API URL in index.html (portable across macOS and Linux)
cat dist/index.html | sed -e "s|API_BASE_URL_PLACEHOLDER|$API_BASE_URL|g" -e "s|VAPID_PUBLIC_KEY_PLACEHOLDER|$VAPID_PUBLIC_KEY|g" > dist/index.html.tmp
mv dist/index.html.tmp dist/index.html

# Build Tailwind CSS
npm run build

echo "Build complete! Output is in dist/"
echo "API URL configured: $API_BASE_URL"
