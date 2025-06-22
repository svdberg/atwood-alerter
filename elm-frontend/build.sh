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

echo "Using API URL: $API_BASE_URL"

# Generate Config.elm from template with the correct API URL
if [ -f src/Config.elm.template ]; then
  cp src/Config.elm.template src/Config.elm.backup
  sed "s|API_BASE_URL_PLACEHOLDER|$API_BASE_URL|g" src/Config.elm.template > src/Config.elm
else
  # Fallback: create Config.elm directly if template doesn't exist
  cp src/Config.elm src/Config.elm.backup
  sed "s|API_BASE_URL_PLACEHOLDER|$API_BASE_URL|g" src/Config.elm.backup > src/Config.elm
fi

# Generate Elm Tailwind modules
npx elm-tailwind-modules --dir src

# Compile Elm code
npx --yes elm make src/Main.elm --output=dist/elm.js --optimize

# Copy public files to dist
cp -r public/* dist/
mkdir -p dist/admin
cp admin/index.html dist/admin/
sed -i '' "s|API_BASE_URL_PLACEHOLDER|$API_BASE_URL|g" dist/admin/index.html

# Replace API URL in index.html as well
sed "s|https://b3q0v6btng.execute-api.eu-north-1.amazonaws.com/prod|$API_BASE_URL|g" dist/index.html > dist/index.html.tmp
mv dist/index.html.tmp dist/index.html

# Build Tailwind CSS
npm run build

# Restore original Config.elm
if [ -f src/Config.elm.template ]; then
  # If using template, restore from template
  cp src/Config.elm.template src/Config.elm
  rm -f src/Config.elm.backup
else
  # If not using template, restore from backup
  mv src/Config.elm.backup src/Config.elm
fi

echo "Build complete! Output is in dist/"
echo "API URL configured: $API_BASE_URL"
