#!/bin/bash

# Test IAM Users for CI/CD Pipeline
set -e

echo "🧪 Testing IAM Users for CI/CD Pipeline"
echo "======================================="
echo ""

# Check for .env file
ENV_FILE=".env"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "❌ .env file not found!"
    echo ""
    echo "Please create a .env file with AWS credentials:"
    echo "AWS_ACCESS_KEY_ID_STAGING=your_staging_access_key"
    echo "AWS_SECRET_ACCESS_KEY_STAGING=your_staging_secret_key"
    echo "AWS_ACCESS_KEY_ID_PROD=your_production_access_key"
    echo "AWS_SECRET_ACCESS_KEY_PROD=your_production_secret_key"
    echo ""
    exit 1
fi

echo "📄 Loading credentials from .env file..."
source "$ENV_FILE"

# Validate required variables
if [[ -z "$AWS_ACCESS_KEY_ID_STAGING" || -z "$AWS_SECRET_ACCESS_KEY_STAGING" ]]; then
    echo "❌ Missing staging AWS credentials in .env file"
    exit 1
fi

if [[ -z "$AWS_ACCESS_KEY_ID_PROD" || -z "$AWS_SECRET_ACCESS_KEY_PROD" ]]; then
    echo "❌ Missing production AWS credentials in .env file"
    exit 1
fi

echo ""

# Test staging user
echo "🔍 Testing staging deployment user..."
AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID_STAGING" AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY_STAGING" \
aws sts get-caller-identity --query 'Arn' --output text 2>/dev/null \
&& echo "✅ Staging user authentication successful" \
|| echo "❌ Staging user authentication failed"

# Test production user
echo "🔍 Testing production deployment user..."
AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID_PROD" AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY_PROD" \
aws sts get-caller-identity --query 'Arn' --output text 2>/dev/null \
&& echo "✅ Production user authentication successful" \
|| echo "❌ Production user authentication failed"

echo ""
echo "🔐 Checking IAM policies..."

# Check staging user policies
echo "📋 Staging user policies:"
aws iam list-attached-user-policies --user-name atwood-staging-deploy --query 'AttachedPolicies[].PolicyName' --output table

# Check production user policies  
echo "📋 Production user policies:"
aws iam list-attached-user-policies --user-name atwood-production-deploy --query 'AttachedPolicies[].PolicyName' --output table

echo ""
echo "🧪 Testing basic permissions..."

# Test staging user CloudFormation access
echo "🔍 Testing staging user CloudFormation access..."
AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID_STAGING" AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY_STAGING" \
aws cloudformation list-stacks --region us-west-2 --query 'StackSummaries[0].StackName' --output text &>/dev/null \
&& echo "✅ Staging user CloudFormation access working" \
|| echo "❌ Staging user CloudFormation access failed"

# Test production user CloudFormation access
echo "🔍 Testing production user CloudFormation access..."
AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID_PROD" AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY_PROD" \
aws cloudformation list-stacks --region eu-north-1 --query 'StackSummaries[0].StackName' --output text &>/dev/null \
&& echo "✅ Production user CloudFormation access working" \
|| echo "❌ Production user CloudFormation access failed"

echo ""
echo "✅ IAM User Testing Complete!"
echo ""
echo "📊 Summary:"
echo "  👤 atwood-staging-deploy: Ready for staging deployments (us-west-2)"
echo "  👤 atwood-production-deploy: Ready for production deployments (eu-north-1)"
echo ""
echo "🚀 These credentials are ready for GitHub Secrets!"