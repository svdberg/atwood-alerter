#!/bin/bash

# GitHub Secrets Setup Script for Atwood Monitor CI/CD
set -e

echo "🔐 GitHub Secrets Setup for Atwood Monitor"
echo "==========================================="
echo ""

# Check if GitHub CLI is installed and authenticated
if ! command -v gh &> /dev/null; then
    echo "❌ GitHub CLI is not installed. Please install it first:"
    echo "   brew install gh"
    exit 1
fi

# Check authentication
if ! gh auth status &> /dev/null; then
    echo "❌ You are not authenticated with GitHub CLI."
    echo "   Please run: gh auth login"
    exit 1
fi

echo "✅ GitHub CLI is authenticated"
echo ""

# Get repository info
REPO_INFO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
echo "📂 Repository: $REPO_INFO"
echo ""

# Confirm before proceeding
read -p "🔍 Do you want to set up GitHub secrets for this repository? (y/N): " -r
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "⏹️  Setup cancelled."
    exit 0
fi

# Check for .env file
ENV_FILE=".env"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "❌ .env file not found!"
    echo ""
    echo "Please create a .env file with the following format:"
    echo ""
    echo "# AWS Staging Environment"
    echo "AWS_ACCESS_KEY_ID_STAGING=your_staging_access_key"
    echo "AWS_SECRET_ACCESS_KEY_STAGING=your_staging_secret_key"
    echo ""
    echo "# AWS Production Environment"
    echo "AWS_ACCESS_KEY_ID_PROD=your_production_access_key"
    echo "AWS_SECRET_ACCESS_KEY_PROD=your_production_secret_key"
    echo ""
    echo "# VAPID Keys (optional, can be added later)"
    echo "VAPID_PRIVATE_KEY=your_vapid_private_key"
    echo "VAPID_PUBLIC_KEY=your_vapid_public_key"
    echo ""
    echo "# Optional: CodeCov token"
    echo "CODECOV_TOKEN=your_codecov_token"
    echo ""
    exit 1
fi

echo "📄 Loading credentials from .env file..."
source "$ENV_FILE"

echo ""
echo "🔧 Setting up AWS credentials for CI/CD..."

# Validate required variables
if [[ -z "$AWS_ACCESS_KEY_ID_STAGING" || -z "$AWS_SECRET_ACCESS_KEY_STAGING" ]]; then
    echo "❌ Missing staging AWS credentials in .env file"
    exit 1
fi

if [[ -z "$AWS_ACCESS_KEY_ID_PROD" || -z "$AWS_SECRET_ACCESS_KEY_PROD" ]]; then
    echo "❌ Missing production AWS credentials in .env file"
    exit 1
fi

# AWS Credentials for Staging
echo "📝 Setting AWS credentials for staging environment..."
gh secret set AWS_ACCESS_KEY_ID_STAGING --body "$AWS_ACCESS_KEY_ID_STAGING"
gh secret set AWS_SECRET_ACCESS_KEY_STAGING --body "$AWS_SECRET_ACCESS_KEY_STAGING"
echo "✅ Staging AWS credentials set"

# AWS Credentials for Production  
echo "📝 Setting AWS credentials for production environment..."
gh secret set AWS_ACCESS_KEY_ID_PROD --body "$AWS_ACCESS_KEY_ID_PROD"
gh secret set AWS_SECRET_ACCESS_KEY_PROD --body "$AWS_SECRET_ACCESS_KEY_PROD"
echo "✅ Production AWS credentials set"

# VAPID Keys (if provided)
if [[ -n "$VAPID_PRIVATE_KEY" && -n "$VAPID_PUBLIC_KEY" ]]; then
    echo "📝 Setting VAPID keys..."
    gh secret set VAPID_PRIVATE_KEY --body "$VAPID_PRIVATE_KEY"
    gh secret set VAPID_PUBLIC_KEY --body "$VAPID_PUBLIC_KEY"
    echo "✅ VAPID keys set"
    VAPID_STATUS="✅ VAPID keys configured"
else
    VAPID_STATUS="⏳ VAPID keys (pending - not in .env file)"
fi

# Optional: CodeCov token
if [[ -n "$CODECOV_TOKEN" ]]; then
    echo "📝 Setting CodeCov token..."
    gh secret set CODECOV_TOKEN --body "$CODECOV_TOKEN"
    echo "✅ CodeCov token set"
    CODECOV_STATUS="✅ CodeCov token configured"
else
    CODECOV_STATUS="⏭️  CodeCov token (not in .env file)"
fi

echo ""
echo "📋 Verifying secrets..."
echo ""
echo "📊 Repository secrets:"
gh secret list

echo ""
echo "✅ GitHub Secrets Setup Complete!"
echo ""
echo "🎯 Summary:"
echo "  ✅ AWS staging credentials configured"
echo "  ✅ AWS production credentials configured"
echo "  $VAPID_STATUS"
echo "  $CODECOV_STATUS"
echo ""
echo "🚀 Next Steps:"
echo "  1. Continue to Step 4: VAPID Keys setup"
echo "  2. Test the CI/CD pipeline"
echo "  3. Review the workflow files in .github/workflows/"
echo ""
echo "📚 For more information, see: scripts/setup-github-secrets.md"