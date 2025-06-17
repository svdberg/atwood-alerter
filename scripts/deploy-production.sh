#!/bin/bash

# Deploy to production environment
set -e

echo "🚀 Deploying to Production Environment"

# Confirmation prompt
echo "⚠️  You are about to deploy to PRODUCTION!"
read -p "Are you sure you want to continue? (yes/no): " -r
if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo "Production deployment cancelled."
    exit 1
fi

# Set environment and region
export ENVIRONMENT=production
export AWS_DEFAULT_REGION=eu-north-1

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

# Run comprehensive tests
echo "🧪 Running post-deployment verification..."
python scripts/verify-deployment.py

echo "✅ Production deployment completed!"
echo "🌐 Check your production domain: https://atwood-sniper.com"
echo "📊 Monitor the deployment: https://console.aws.amazon.com/cloudwatch/home?region=eu-north-1#dashboards:name=WebPushDashboard"