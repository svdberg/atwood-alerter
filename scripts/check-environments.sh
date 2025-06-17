#!/bin/bash

# Environment status check script
set -e

echo "🌍 Atwood Monitor - Environment Status Check"
echo "=============================================="
echo ""

# Function to check bootstrap status
check_bootstrap() {
    local env_name=$1
    local region=$2
    local status=$(aws cloudformation describe-stacks --stack-name CDKToolkit --region $region --query 'Stacks[0].StackStatus' --output text 2>/dev/null || echo "NOT_BOOTSTRAPPED")
    
    if [ "$status" = "CREATE_COMPLETE" ]; then
        echo "✅ $env_name ($region): Bootstrapped"
    else
        echo "❌ $env_name ($region): Not bootstrapped"
    fi
}

# Check all environments
echo "📊 CDK Bootstrap Status:"
check_bootstrap "Production" "eu-north-1"
check_bootstrap "Staging" "us-west-2"

echo ""
echo "🧪 CDK Synthesis Test:"

# Test synthesis for each environment
for env in staging production; do
    echo -n "📍 Testing $env environment: "
    if ENVIRONMENT=$env cdk synth --all 1>/dev/null 2>&1; then
        echo "✅ Success"
    else
        echo "❌ Failed"
    fi
done

echo ""
echo "🔧 Available Deployment Commands:"
echo "  Staging:     ./scripts/deploy-staging.sh"
echo "  Production:  ./scripts/deploy-production.sh"

echo ""
echo "📚 Environment Details:"
echo "  Staging:     us-west-2  → staging.atwood-sniper.com"
echo "  Production:  eu-north-1 → atwood-sniper.com"

echo ""
echo "💰 Cost Optimization:"
echo "  - Using only 2 environments (staging + production)"
echo "  - Staging in us-west-2 for isolation and testing"
echo "  - Production in eu-north-1 for optimal performance"