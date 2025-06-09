# frontend.py

from aws_cdk import Duration, RemovalPolicy, CfnOutput
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3deploy
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_route53_targets as route53_targets
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_iam as iam
from constructs import Construct


def setup_frontend(scope: Construct, certificate_arn: str, webpush_lambda):
    # 1. S3 Bucket
    site_bucket = s3.Bucket(
        scope, "FrontendBucket",
        website_index_document="index.html",
        public_read_access=False,
        block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        removal_policy=RemovalPolicy.DESTROY,
        auto_delete_objects=True
    )

    # 2. OAI for CloudFront
    oai = cloudfront.OriginAccessIdentity(scope, "FrontendOAI")

    site_bucket.add_to_resource_policy(
        iam.PolicyStatement(
            actions=["s3:GetObject"],
            resources=[f"{site_bucket.bucket_arn}/*"],
            principals=[iam.CanonicalUserPrincipal(oai.cloud_front_origin_access_identity_s3_canonical_user_id)]
        )
    )

    # 3. Hosted Zone and TLS Cert
    hosted_zone = route53.HostedZone.from_lookup(scope, "HostedZone", domain_name="atwood-sniper.com")

    certificate = acm.Certificate.from_certificate_arn(
        scope, "ImportedCert", certificate_arn
    )

    # 4. CloudFront Distribution
    distribution = cloudfront.Distribution(
        scope, "FrontendDistribution",
        default_behavior=cloudfront.BehaviorOptions(
            origin=origins.S3Origin(site_bucket, origin_access_identity=oai),
            viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS
        ),
        domain_names=["atwood-sniper.com"],
        certificate=certificate,
        default_root_object="index.html"
    )

    # 5. Route53 ARecord
    route53.ARecord(
        scope, "AliasRecord",
        zone=hosted_zone,
        record_name="atwood-sniper.com",
        target=route53.RecordTarget.from_alias(
            route53_targets.CloudFrontTarget(distribution)
        )
    )

    # 6. Deployment to S3 + Cache Invalidation
    s3deploy.BucketDeployment(
        scope, "DeployFrontend",
        sources=[s3deploy.Source.asset("elm-frontend/dist")],
        destination_bucket=site_bucket,
        distribution=distribution,
        distribution_paths=["/*"]
    )

    # 7. Output the URL
    CfnOutput(scope, "FrontendURL", value=f"https://{distribution.distribution_domain_name}")
