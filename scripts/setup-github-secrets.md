# GitHub Secrets Setup Guide

This guide helps you configure the required GitHub repository secrets for the CI/CD pipeline.

## Prerequisites

1. **GitHub CLI Authentication**:
   ```bash
   gh auth login
   ```

2. **Repository Access**: Ensure you have admin access to your GitHub repository.

## Required Secrets

### 1. AWS Credentials for Staging Environment

```bash
# Set staging AWS credentials
gh secret set AWS_ACCESS_KEY_ID_STAGING --body "<KEY>"
gh secret set AWS_SECRET_ACCESS_KEY_STAGING --body "<KEY_STAGING>"
```

### 2. AWS Credentials for Production Environment

```bash
# Set production AWS credentials  
gh secret set AWS_ACCESS_KEY_ID_PROD --body "<KEY>"
gh secret set AWS_SECRET_ACCESS_KEY_PROD --body "<KEY_STAGING>"
```

### 3. VAPID Keys (Web Push Notifications)

These will be generated in Step 4, but you'll need to set them as secrets:

```bash
# VAPID keys (to be generated in Step 4)
gh secret set VAPID_PRIVATE_KEY --body "YOUR_VAPID_PRIVATE_KEY"
gh secret set VAPID_PUBLIC_KEY --body "YOUR_VAPID_PUBLIC_KEY"
```

### 4. Optional: CodeCov Token

For code coverage reporting:

```bash
# Optional: CodeCov token for coverage reports
gh secret set CODECOV_TOKEN --body "YOUR_CODECOV_TOKEN"
```

## Environment Variables

In addition to secrets, you may want to set these environment variables in your GitHub Actions workflow:

| Variable | Value | Description |
|----------|-------|-------------|
| `AWS_REGION_STAGING` | `us-west-2` | AWS region for staging environment |
| `AWS_REGION_PRODUCTION` | `eu-north-1` | AWS region for production environment |
| `PYTHON_VERSION` | `3.11` | Python version for CI/CD |
| `NODE_VERSION` | `18` | Node.js version for frontend builds |

## Verification

After setting up the secrets, verify they're configured correctly:

```bash
# List all repository secrets
gh secret list

# Check specific secret (won't show value, just confirms it exists)
gh secret get AWS_ACCESS_KEY_ID_STAGING
```

## Security Notes

⚠️ **Important Security Considerations**:

1. **Least Privilege**: The IAM users created have deployment permissions but are scoped to necessary services only.

2. **Rotation**: Consider rotating these access keys periodically:
   ```bash
   # To rotate keys later:
   aws iam create-access-key --user-name atwood-staging-deploy
   aws iam delete-access-key --user-name atwood-staging-deploy --access-key-id OLD_KEY_ID
   ```

3. **Monitoring**: Monitor AWS CloudTrail for these user activities.

4. **Separate Users**: Each environment has its own IAM user for better security isolation.

## IAM Users Created

| User | Purpose | Permissions | Region Access |
|------|---------|-------------|---------------|
| `atwood-staging-deploy` | Staging CI/CD | CDK deployment + AWS services | us-west-2 |
| `atwood-production-deploy` | Production CI/CD | CDK deployment + AWS services | eu-north-1 |

## Next Steps

1. Run the secret setup commands above
2. Continue to Step 4: VAPID Keys setup
3. Test the CI/CD pipeline with a sample commit

## Troubleshooting

**If secrets don't work**:
1. Verify GitHub CLI is authenticated: `gh auth status`
2. Check repository permissions: `gh repo view`
3. Ensure secret names match exactly (case-sensitive)
4. Test AWS credentials locally first

**If deployments fail**:
1. Check IAM policy permissions
2. Verify CDK bootstrap is complete in target regions
3. Review CloudFormation stack events for detailed errors