from aws_cdk import (
    Stack, Duration,
    aws_lambda as lambda_,
    aws_dynamodb as dynamodb,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_apigateway as apigateway,
    aws_sns as sns,
    aws_sns_subscriptions as subscriptions,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_cloudwatch as cw,
    aws_route53 as route53,
    aws_route53_targets as route53_targets,
    aws_certificatemanager as acm,
    RemovalPolicy, CfnOutput,
)
from constructs import Construct
from aws_cdk.aws_ecr_assets import Platform

from .lambdas import (
    create_lambda_layer,
    create_lambda_role,
    create_scraper_lambda,
    create_status_lambda,
    create_subscribe_lambda,
    create_web_push_lambda,
    create_register_web_push_lambda
)
from .storage import create_tables
from .frontend import setup_frontend
from .api_gateway import setup_api_gateway
from .monitoring import setup_dashboard


class AtwoodMonitorStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, certificate_arn: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # DynamoDB and SNS setup
        posts_table, users_table, web_push_table, notify_topic, web_notify_topic = create_tables(self)

        # Lambda functions
        lambda_layer = create_lambda_layer(self)
        lambda_role = create_lambda_role(self)
        scraper_lambda = create_scraper_lambda(self, lambda_role, lambda_layer, posts_table, users_table, notify_topic)
        status_lambda = create_status_lambda(self, lambda_role, lambda_layer, posts_table)
        subscribe_lambda = create_subscribe_lambda(self, lambda_role, lambda_layer, users_table, notify_topic)
        webpush_lambda = create_web_push_lambda(self, web_push_table, web_notify_topic)
        register_web_push_lambda = create_register_web_push_lambda(self, lambda_role, web_push_table)

        # EventBridge trigger for scraping
        rule = events.Rule(
            self, "ScrapeSchedule",
            schedule=events.Schedule.rate(Duration.minutes(1))
        )
        rule.add_target(targets.LambdaFunction(scraper_lambda))

        # API Gateway setup
        api = setup_api_gateway(
            self,
            status_lambda=status_lambda,
            subscribe_lambda=subscribe_lambda,
            register_web_push_lambda=register_web_push_lambda
        )

        # Frontend setup with S3, CloudFront, Route53
        setup_frontend(self, certificate_arn, webpush_lambda)

        # Monitoring Dashboard
        setup_dashboard(self)

        # Output
        CfnOutput(self, "StackStatus", value="Deployment completed")
