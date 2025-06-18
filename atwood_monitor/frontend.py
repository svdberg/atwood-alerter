# frontend.py

import os

from aws_cdk import CfnOutput, RemovalPolicy
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_iam as iam
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_route53_targets as route53_targets
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3deploy
from constructs import Construct

from .environments import EnvironmentConfig


def setup_frontend(
    scope: Construct,
    certificate_arn: str,
    webpush_lambda,
    env_config: EnvironmentConfig,
):
    # 1. S3 Bucket
    site_bucket = s3.Bucket(
        scope,
        "FrontendBucket",
        bucket_name=f"{env_config.resource_name_prefix}-frontend",
        website_index_document="index.html",
        public_read_access=False,
        block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        removal_policy=(
            RemovalPolicy.DESTROY
            if env_config.name != "production"
            else RemovalPolicy.RETAIN
        ),
        auto_delete_objects=True if env_config.name != "production" else False,
    )

    # 2. OAI for CloudFront
    oai = cloudfront.OriginAccessIdentity(scope, "FrontendOAI")

    site_bucket.add_to_resource_policy(
        iam.PolicyStatement(
            actions=["s3:GetObject"],
            resources=[f"{site_bucket.bucket_arn}/*"],
            principals=[
                iam.CanonicalUserPrincipal(
                    oai.cloud_front_origin_access_identity_s3_canonical_user_id
                )
            ],
        )
    )

    # 3. Hosted Zone and TLS Cert
    base_domain = env_config.domain_name.split(".")[
        -2:
    ]  # Get base domain (atwood-sniper.com)
    base_domain_name = ".".join(base_domain)

    hosted_zone = route53.HostedZone.from_lookup(
        scope, "HostedZone", domain_name=base_domain_name
    )

    certificate = acm.Certificate.from_certificate_arn(
        scope, "ImportedCert", certificate_arn
    )

    # 4. CloudFront Distribution
    distribution = cloudfront.Distribution(
        scope,
        "FrontendDistribution",
        default_behavior=cloudfront.BehaviorOptions(
            origin=origins.S3Origin(site_bucket, origin_access_identity=oai),
            viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        ),
        domain_names=[env_config.domain_name],
        certificate=certificate,
        default_root_object="index.html",
        comment=f"Frontend distribution for {env_config.name} environment",
    )

    # 5. Route53 ARecord
    route53.ARecord(
        scope,
        "AliasRecord",
        zone=hosted_zone,
        record_name=env_config.domain_name,
        target=route53.RecordTarget.from_alias(
            route53_targets.CloudFrontTarget(distribution)
        ),
    )

    # 6. Deployment to S3 + Cache Invalidation
    if os.path.exists("elm-frontend/dist"):
        s3deploy.BucketDeployment(
            scope,
            "DeployFrontend",
            sources=[s3deploy.Source.asset("elm-frontend/dist")],
            destination_bucket=site_bucket,
            distribution=distribution,
            distribution_paths=["/*"],
        )

    # 7. Output the URL
    CfnOutput(scope, "FrontendURL", value=f"https://{env_config.domain_name}")
    CfnOutput(
        scope, "CloudFrontURL", value=f"https://{distribution.distribution_domain_name}"
    )
    CfnOutput(scope, "S3BucketName", value=site_bucket.bucket_name)
