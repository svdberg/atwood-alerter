from aws_cdk import (
   Stack,
   aws_route53 as route53,
   aws_certificatemanager as acm,
)
from constructs import Construct


class CertificateStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        hosted_zone = route53.HostedZone.from_lookup(
            self, "HostedZone",
            domain_name="atwood-sniper.com"
        )

        self.certificate = acm.Certificate(
            self, "SiteCert",
            domain_name="atwood-sniper.com",
            validation=acm.CertificateValidation.from_dns(hosted_zone)
        )
