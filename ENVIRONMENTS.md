# Environment Configuration

This project uses a **two-environment setup** for cost optimization while maintaining proper staging/production isolation.

## 🌍 Environments

| Environment | Region | Domain | Purpose | Schedule |
|-------------|---------|---------|----------|----------|
| **Staging** | us-west-2 | staging.atwood-sniper.com | Testing & validation | Every 2 minutes |
| **Production** | eu-north-1 | atwood-sniper.com | Live environment | Every 1 minute |

## 🏗️ Infrastructure

### Regional Isolation
- **Staging**: us-west-2 for complete isolation from production
- **Production**: eu-north-1 for optimal European performance

### Resource Naming
- **Staging**: `atwood-staging-*` resources
- **Production**: `atwood-production-*` resources

### Environment Variables
All Lambda functions receive:
- `ENVIRONMENT`: staging|production
- `DEBUG`: true|false (based on environment)

## 🚀 Deployment

### Prerequisites
1. AWS CDK bootstrapped in both regions ✅
2. Route53 hosted zone for atwood-sniper.com
3. SSL certificates for domains
4. GitHub repository secrets configured

### Commands
```bash
# Deploy to staging
./scripts/deploy-staging.sh

# Deploy to production
./scripts/deploy-production.sh

# Check environment status
./scripts/check-environments.sh
```

### Environment Variables
Set these before deployment:
```bash
# For staging
export ENVIRONMENT=staging
export AWS_DEFAULT_REGION=us-west-2

# For production
export ENVIRONMENT=production
export AWS_DEFAULT_REGION=eu-north-1
```

## 💰 Cost Optimization

### Design Decisions
- **Two environments only** (vs typical dev/staging/production)
- **Regional separation** for true isolation
- **Different schedules** (2min staging vs 1min production)
- **Debug mode** only in staging
- **Monitoring** enabled in both environments

### Resource Lifecycle
- **Staging**: Resources have DESTROY removal policy
- **Production**: Resources have RETAIN removal policy for safety

## 🔐 Security

### Isolation
- Complete regional separation
- Environment-specific IAM roles
- Separate DynamoDB tables and SNS topics

### Monitoring
- CloudWatch dashboards for both environments
- Environment-specific metrics and alarms
- Separate log groups per environment

## 🧪 Testing

### Validation
```bash
# Test configuration
./scripts/check-environments.sh

# Test CDK synthesis
ENVIRONMENT=staging cdk synth --all
ENVIRONMENT=production cdk synth --all
```

### CI/CD Pipeline
- **Staging**: Deployed on main branch push
- **Production**: Deployed on tagged releases
- **Integration tests**: Run against staging
- **Smoke tests**: Run against production post-deployment

## 📊 Monitoring

### Staging Environment
- Used for testing new features
- Debug logging enabled
- Less frequent scraping (cost optimization)
- Automatic resource cleanup

### Production Environment
- Live blog monitoring
- Optimized performance settings
- Full monitoring and alerting
- Data retention and backups