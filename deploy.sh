#!/bin/bash

echo "🚀 Starting deployment process..."

echo "📦 Building Elm frontend..."
cd elm-frontend
./build.sh
if [ $? -ne 0 ]; then
    echo "❌ Frontend build failed!"
    exit 1
fi
echo "✅ Frontend build complete"

echo "🔄 Deploying to AWS..."
cd ..
cdk deploy --all
if [ $? -ne 0 ]; then
    echo "❌ AWS deployment failed!"
    exit 1
fi

echo "✅ Deployment complete! Your app should be live in a few minutes."
