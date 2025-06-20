#!/bin/bash

# Deploy to staging environment
set -e

echo "🚀 Deploying to Staging Environment"

# Set environment and region
export ENVIRONMENT=staging
export AWS_DEFAULT_REGION=us-west-2
if [ -n "$ADMIN_SECRET" ]; then
  aws ssm put-parameter --name "/atwood/staging/admin_secret" --value "$ADMIN_SECRET" --type "SecureString" --overwrite
fi

# Build the Lambda layer
echo "📦 Building Lambda layer..."
./build-layer-with-docker.sh

# Build frontend
echo "🎨 Building frontend..."
cd elm-frontend
./build.sh
cd ..

# Deploy with CDK
echo "☁️ Deploying infrastructure..."
cdk deploy --all --require-approval never

# Run smoke tests
echo "🧪 Running smoke tests..."
python scripts/verify-deployment.py

echo "✅ Staging deployment completed!"
echo "🌐 Check your staging domain: https://staging.atwood-sniper.com"