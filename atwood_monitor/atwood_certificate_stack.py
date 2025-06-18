from aws_cdk import Stack
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_route53 as route53
from constructs import Construct

from .environments import EnvironmentConfig


class CertificateStack(Stack):
    def __init__(
        self, scope: Construct, id: str, env_config: EnvironmentConfig, **kwargs
    ):
        super().__init__(scope, id, **kwargs)

        self.env_config = env_config

        # Always use the base domain for the hosted zone
        base_domain = "atwood-sniper.com"
        hosted_zone = route53.HostedZone.from_lookup(
            self, "HostedZone", domain_name=base_domain
        )

        # Create a wildcard certificate that covers all subdomains
        # This single certificate works for both staging and production
        self.certificate = acm.Certificate(
            self,
            "WildcardCert",
            domain_name=base_domain,  # Primary domain: atwood-sniper.com
            subject_alternative_names=[
                f"*.{base_domain}"
            ],  # Wildcard: *.atwood-sniper.com
            validation=acm.CertificateValidation.from_dns(hosted_zone),
            certificate_name="atwood-sniper-wildcard-cert",
        )
