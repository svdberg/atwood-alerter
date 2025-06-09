#!/usr/bin/env python3
import aws_cdk as cdk
from atwood_monitor.atwood_monitor_stack import AtwoodMonitorStack
from atwood_monitor.atwood_certificate_stack import CertificateStack

app = cdk.App()

cert_stack = CertificateStack(app, "CertificateStack",
    env=cdk.Environment(account="242650470527", region="us-east-1")
)

main_stack = AtwoodMonitorStack(app, "AtwoodMonitorStack",
    env=cdk.Environment(account="242650470527", region="eu-north-1"),
    certificate_arn=cert_stack.certificate.certificate_arn,
    cross_region_references=True
)

app.synth()
