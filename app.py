#!/usr/bin/env python3

import aws_cdk as cdk

from atwood_monitor.atwood_certificate_stack import CertificateStack
from atwood_monitor.atwood_monitor_stack import AtwoodMonitorStack
from atwood_monitor.environments import get_current_environment

app = cdk.App()

# Get environment configuration
env_config = get_current_environment()

# Certificate stack (always in us-east-1 for CloudFront)
# Create one wildcard certificate that works for both environments
cert_stack = CertificateStack(
    app,
    "AtwoodMonitor-Certificate",  # Single certificate stack
    env=cdk.Environment(account=env_config.account, region="us-east-1"),
    env_config=env_config,
)

# Export certificate ARN for cross-region use
cdk.CfnOutput(
    cert_stack,
    "CertificateArnExport",
    value=cert_stack.certificate.certificate_arn,
    export_name=f"AtwoodMonitor-Certificate-Arn-{env_config.name}",
)

# Use hardcoded certificate ARNs to avoid cross-region CloudFormation export limitations
# Both staging and production use the same wildcard certificate
certificate_arn = "arn:aws:acm:us-east-1:242650470527:certificate/b809c213-3c61-4e30-b46c-81a6ac5c76cd"

main_stack = AtwoodMonitorStack(
    app,
    f"{env_config.stack_name_prefix}-Main",
    env=cdk.Environment(account=env_config.account, region=env_config.region),
    certificate_arn=certificate_arn,
    env_config=env_config,
)

app.synth()
