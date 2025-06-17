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
    env_config=env_config
)

# Main stack
main_stack = AtwoodMonitorStack(
    app,
    f"{env_config.stack_name_prefix}-Main",
    env=cdk.Environment(account=env_config.account, region=env_config.region),
    certificate_arn=cert_stack.certificate.certificate_arn,
    env_config=env_config,
    cross_region_references=True
)

app.synth()
