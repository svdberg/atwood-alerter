# GitHub CI/CD Setup Guide

## Overview

This guide helps you set up GitHub repository secrets and CI/CD pipeline for the Atwood Monitor project.

## 🔐 Step 1: Authenticate with GitHub CLI

```bash
# Install GitHub CLI (if not already installed)
brew install gh

# Authenticate with GitHub
gh auth login
```

## 🤖 Step 2: Set Up Repository Secrets

### Option A: Automated Setup (Recommended)

```bash
# Run the automated setup script
./scripts/setup-github-secrets.sh
```

### Option B: Manual Setup

```bash
# AWS Staging Environment Credentials
gh secret set AWS_ACCESS_KEY_ID_STAGING --body "<KEY>"
gh secret set AWS_SECRET_ACCESS_KEY_STAGING --body "<KEY_STAGING>"

# AWS Production Environment Credentials  
gh secret set AWS_ACCESS_KEY_ID_PROD --body "<KEY>>"
gh secret set AWS_SECRET_ACCESS_KEY_PROD --body "<KEY_PROD>"

# VAPID Keys (to be added in Step 4)
# gh secret set VAPID_PRIVATE_KEY --body "YOUR_VAPID_PRIVATE_KEY"
# gh secret set VAPID_PUBLIC_KEY --body "YOUR_VAPID_PUBLIC_KEY"
```

## 🔍 Step 3: Verify Setup

```bash
# List all repository secrets
gh secret list

# Test IAM users (optional)
./scripts/test-iam-users.sh
```

## 📋 Required Secrets Summary

| Secret Name | Purpose | Status |
|-------------|---------|---------|
| `AWS_ACCESS_KEY_ID_STAGING` | Staging deployment credentials | ✅ Ready |
| `AWS_SECRET_ACCESS_KEY_STAGING` | Staging deployment credentials | ✅ Ready |
| `AWS_ACCESS_KEY_ID_PROD` | Production deployment credentials | ✅ Ready |
| `AWS_SECRET_ACCESS_KEY_PROD` | Production deployment credentials | ✅ Ready |
| `VAPID_PRIVATE_KEY` | Web push notifications | ⏳ Pending Step 4 |
| `VAPID_PUBLIC_KEY` | Web push notifications | ⏳ Pending Step 4 |

## 🏗️ IAM Users Created

| User | Environment | Permissions | Region |
|------|-------------|-------------|---------|
| `atwood-staging-deploy` | Staging | CDK + AWS services | us-west-2 |
| `atwood-production-deploy` | Production | CDK + AWS services | eu-north-1 |

## 🔐 Security Features

- **Least Privilege**: Each user has minimal required permissions
- **Environment Isolation**: Separate users for staging/production
- **Policy-Based Access**: Custom IAM policies for precise control
- **Regional Restrictions**: Users scoped to their respective regions

## 🚀 CI/CD Pipeline Workflow

Once secrets are configured, the pipeline will:

1. **On Pull Request**: Run tests and security scans
2. **On Main Branch Push**: Deploy to staging environment
3. **On Tagged Release**: Deploy to production environment

### Deployment Flow

```
Pull Request → Security Scan + Tests
     ↓
Main Branch → Deploy to Staging → Integration Tests
     ↓
Tag Release → Deploy to Production → Smoke Tests
```

## 📊 Environment Details

| Environment | Region | Domain | Stack Name |
|-------------|---------|---------|-------------|
| Staging | us-west-2 | staging.atwood-sniper.com | AtwoodMonitor-Staging-Main |
| Production | eu-north-1 | atwood-sniper.com | AtwoodMonitor-Production-Main |

## 🔧 Troubleshooting

### Authentication Issues

```bash
# Check GitHub CLI authentication
gh auth status

# Re-authenticate if needed
gh auth logout
gh auth login
```

### Permission Issues

```bash
# Test IAM user permissions
./scripts/test-iam-users.sh

# Check secret values (won't show actual values)
gh secret get AWS_ACCESS_KEY_ID_STAGING
```

### Deployment Issues

```bash
# Check CloudFormation stack status
aws cloudformation describe-stacks --stack-name AtwoodMonitor-Staging-Main --region us-west-2
aws cloudformation describe-stacks --stack-name AtwoodMonitor-Production-Main --region eu-north-1
```

## 📚 Next Steps

1. ✅ Complete Step 3: GitHub Secrets configuration
2. ⏳ Continue to Step 4: VAPID Keys setup
3. 🚀 Test the CI/CD pipeline with a sample commit
4. 📈 Monitor deployments in GitHub Actions

## 📖 Additional Resources

- [GitHub Secrets Documentation](https://docs.github.com/en/actions/security-guides/encrypted-secrets)
- [AWS IAM Best Practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)
- [CDK Deployment Guide](./ENVIRONMENTS.md)