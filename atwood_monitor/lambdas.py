from aws_cdk import (
    Duration,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_sns as sns,
    aws_dynamodb as dynamodb
)

from constructs import Construct
from aws_cdk.aws_ecr_assets import Platform
from aws_cdk import aws_sns_subscriptions as subscriptions
import os
from aws_cdk import aws_ssm as ssm


def create_lambda_layer(scope: Construct) -> lambda_.LayerVersion:
    return lambda_.LayerVersion(
        scope, "LambdaDepsLayer",
        code=lambda_.Code.from_asset("out/layer.zip"),
        compatible_runtimes=[lambda_.Runtime.PYTHON_3_11],
        description="Common Python dependencies for blog monitor"
    )


def create_lambda_role(scope: Construct) -> iam.Role:
    return iam.Role(
        scope, "LambdaExecutionRole",
        assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        managed_policies=[
            iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole")
        ]
    )


def create_scraper_lambda(scope: Construct, role, layer, posts_table, users_table, notify_topic: sns.Topic) -> lambda_.Function:
    fn = lambda_.Function(
        scope, "BlogMonitorFunction",
        function_name="AtwoodBlogMonitor",
        runtime=lambda_.Runtime.PYTHON_3_11,
        handler="lambda_function.lambda_handler",
        timeout=Duration.seconds(30),
        code=lambda_.Code.from_asset("lambda"),
        environment={
            "POSTS_TABLE": posts_table.table_name,
            "USERS_TABLE": users_table.table_name,
            "NOTIFY_TOPIC_ARN": notify_topic.topic_arn
        },
        layers=[layer],
        role=role
    )

    posts_table.grant_read_write_data(fn)
    users_table.grant_read_data(fn)
    notify_topic.grant_publish(fn)
    return fn


def create_status_lambda(scope: Construct, role, layer, posts_table) -> lambda_.Function:
    fn = lambda_.Function(
        scope, "StatusLambda",
        function_name="AtwoodStatusPage",
        runtime=lambda_.Runtime.PYTHON_3_11,
        handler="status_lambda.lambda_handler",
        code=lambda_.Code.from_asset("lambda"),
        environment={
            "POSTS_TABLE": posts_table.table_name,
        },
        layers=[layer],
        role=role
    )
    posts_table.grant_read_data(fn)
    return fn


def create_subscribe_lambda(scope: Construct, role, layer, users_table, notify_topic: sns.Topic) -> lambda_.Function:
    fn = lambda_.Function(
        scope, "SubscribeLambda",
        function_name="AtwoodSubscribeHandler",
        runtime=lambda_.Runtime.PYTHON_3_11,
        handler="subscribe_lambda.lambda_handler",
        code=lambda_.Code.from_asset("lambda"),
        environment={
            "USERS_TABLE": users_table.table_name,
            "NOTIFY_TOPIC_ARN": notify_topic.topic_arn
        },
        layers=[layer],
        role=role
    )
    users_table.grant_write_data(fn)
    notify_topic.grant_subscribe(fn)
    return fn


def create_register_web_push_lambda(scope: Construct, role, web_push_table) -> lambda_.Function:
    fn = lambda_.Function(
        scope, "RegisterSubscriptionLambda",
        handler="subscribe_web_lambda.lambda_handler",
        runtime=lambda_.Runtime.PYTHON_3_11,
        code=lambda_.Code.from_asset("lambda"),
        environment={
            "WEB_PUSH_TABLE": web_push_table.table_name
        },
        role=role
    )
    web_push_table.grant_write_data(fn)
    return fn


def create_web_push_lambda(scope: Construct, web_push_table, web_notify_topic) -> lambda_.DockerImageFunction:
    vapid_private_key = ssm.StringParameter.value_for_secure_string_parameter(
        scope, "/atwood/vapid_private_key"
    )
    vapid_public_key = ssm.StringParameter.value_for_string_parameter(
        scope, "/atwood/vapid_public_key"
    )

    webpush_lambda = lambda_.DockerImageFunction(
        scope, "WebPushLambda",
        code=lambda_.DockerImageCode.from_image_asset(
            "lambda/lambda-docker",
            platform=Platform.LINUX_AMD64
        ),
        environment={
            "VAPID_PUBLIC_KEY": vapid_public_key,
            "VAPID_PRIVATE_KEY": vapid_private_key
        },
        timeout=Duration.seconds(30)
    )

    web_push_table.grant_read_write_data(webpush_lambda)

    web_notify_topic.add_subscription(
        subscriptions.LambdaSubscription(webpush_lambda)
    )

    webpush_lambda.add_to_role_policy(
        iam.PolicyStatement(
            actions=["cloudwatch:PutMetricData"],
            resources=["*"],
            effect=iam.Effect.ALLOW,
        )
    )

    return webpush_lambda

