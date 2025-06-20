import os

from aws_cdk import Duration
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subscriptions
from aws_cdk.aws_ecr_assets import Platform
from constructs import Construct

from .environments import EnvironmentConfig


def create_lambda_layer(
    scope: Construct, env_config: EnvironmentConfig
) -> lambda_.LayerVersion:
    return lambda_.LayerVersion(
        scope,
        "LambdaDepsLayer",
        code=lambda_.Code.from_asset("out/layer.zip"),
        compatible_runtimes=[lambda_.Runtime.PYTHON_3_11],
        description=f"Common Python dependencies for blog monitor ({env_config.name})",
        layer_version_name=f"{env_config.resource_name_prefix}-dependencies",
    )


def create_lambda_role(scope: Construct, env_config: EnvironmentConfig) -> iam.Role:
    return iam.Role(
        scope,
        "LambdaExecutionRole",
        role_name=f"{env_config.resource_name_prefix}-lambda-execution-role",
        assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
        managed_policies=[
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AWSLambdaBasicExecutionRole"
            )
        ],
    )


def create_scraper_lambda(
    scope: Construct,
    role,
    layer,
    posts_table,
    users_table,
    notify_topic: sns.Topic,
    env_config: EnvironmentConfig,
) -> lambda_.Function:
    fn = lambda_.Function(
        scope,
        "BlogMonitorFunction",
        function_name=f"{env_config.resource_name_prefix}-blog-monitor",
        runtime=lambda_.Runtime.PYTHON_3_11,
        handler="lambda_function.lambda_handler",
        timeout=Duration.seconds(30),
        code=lambda_.Code.from_asset("lambda"),
        environment={
            "POSTS_TABLE": posts_table.table_name,
            "USERS_TABLE": users_table.table_name,
            "NOTIFY_TOPIC_ARN": notify_topic.topic_arn,
            "ENVIRONMENT": env_config.name,
            "DEBUG": str(env_config.debug_mode).lower(),
        },
        layers=[layer],
        role=role,
    )

    posts_table.grant_read_write_data(fn)
    users_table.grant_read_data(fn)
    notify_topic.grant_publish(fn)
    return fn


def create_status_lambda(
    scope: Construct, role, layer, posts_table, env_config: EnvironmentConfig
) -> lambda_.Function:
    fn = lambda_.Function(
        scope,
        "StatusLambda",
        function_name=f"{env_config.resource_name_prefix}-status",
        runtime=lambda_.Runtime.PYTHON_3_11,
        handler="status_lambda.lambda_handler",
        code=lambda_.Code.from_asset("lambda"),
        environment={
            "POSTS_TABLE": posts_table.table_name,
            "ENVIRONMENT": env_config.name,
            "DEBUG": str(env_config.debug_mode).lower(),
        },
        layers=[layer],
        role=role,
    )
    posts_table.grant_read_data(fn)
    return fn


def create_subscribe_lambda(
    scope: Construct,
    role,
    layer,
    users_table,
    notify_topic: sns.Topic,
    env_config: EnvironmentConfig,
) -> lambda_.Function:
    fn = lambda_.Function(
        scope,
        "SubscribeLambda",
        function_name=f"{env_config.resource_name_prefix}-subscribe",
        runtime=lambda_.Runtime.PYTHON_3_11,
        handler="subscribe_lambda.lambda_handler",
        code=lambda_.Code.from_asset("lambda"),
        environment={
            "USERS_TABLE": users_table.table_name,
            "NOTIFY_TOPIC_ARN": notify_topic.topic_arn,
            "ENVIRONMENT": env_config.name,
            "DEBUG": str(env_config.debug_mode).lower(),
        },
        layers=[layer],
        role=role,
    )
    users_table.grant_write_data(fn)
    notify_topic.grant_subscribe(fn)
    return fn


def create_register_web_push_lambda(
    scope: Construct, role, web_push_table, env_config: EnvironmentConfig
) -> lambda_.Function:
    fn = lambda_.Function(
        scope,
        "RegisterSubscriptionLambda",
        function_name=f"{env_config.resource_name_prefix}-register-web-push",
        handler="subscribe_web_lambda.lambda_handler",
        runtime=lambda_.Runtime.PYTHON_3_11,
        code=lambda_.Code.from_asset("lambda"),
        environment={
            "WEB_PUSH_TABLE": web_push_table.table_name,
            "ENVIRONMENT": env_config.name,
            "DEBUG": str(env_config.debug_mode).lower(),
        },
        role=role,
    )
    web_push_table.grant_write_data(fn)
    return fn


def create_web_push_lambda(
    scope: Construct, web_push_table, web_notify_topic, env_config: EnvironmentConfig
) -> lambda_.DockerImageFunction:
    webpush_lambda = lambda_.DockerImageFunction(
        scope,
        "WebPushLambda",
        function_name=f"{env_config.resource_name_prefix}-web-push",
        code=lambda_.DockerImageCode.from_image_asset(
            "lambda/lambda-docker", platform=Platform.LINUX_AMD64
        ),
        timeout=Duration.seconds(30),
        environment={
            "WEB_PUSH_TABLE": web_push_table.table_name,
            "ENVIRONMENT": env_config.name,
            "DEBUG": str(env_config.debug_mode).lower(),
        },
    )

    web_push_table.grant_read_write_data(webpush_lambda)

    web_notify_topic.add_subscription(subscriptions.LambdaSubscription(webpush_lambda))

    webpush_lambda.add_to_role_policy(
        iam.PolicyStatement(
            actions=["cloudwatch:PutMetricData"],
            resources=["*"],
            effect=iam.Effect.ALLOW,
        )
    )

    return webpush_lambda

  
def create_admin_stats_lambda(
    scope: Construct,
    role,
    layer,
    users_table,
    web_push_table,
    env_config: EnvironmentConfig,
) -> lambda_.Function:
    fn = lambda_.Function(
        scope,
        "AdminStatsLambda",
        function_name=f"{env_config.resource_name_prefix}-admin-stats",
        runtime=lambda_.Runtime.PYTHON_3_11,
        handler="admin_stats.lambda_handler",
        code=lambda_.Code.from_asset("lambda"),
        environment={
            "USERS_TABLE": users_table.table_name,
            "WEB_PUSH_TABLE": web_push_table.table_name,
            "ENVIRONMENT": env_config.name,
            "DEBUG": str(env_config.debug_mode).lower(),
        },
        layers=[layer],
        role=role,
    )
    users_table.grant_read_data(fn)
    web_push_table.grant_read_data(fn)
    return fn


def create_admin_delete_lambda(
    scope: Construct,
    role,
    layer,
    users_table,
    web_push_table,
    env_config: EnvironmentConfig,
) -> lambda_.Function:
    fn = lambda_.Function(
        scope,
        "AdminDeleteLambda",
        function_name=f"{env_config.resource_name_prefix}-admin-delete",
        runtime=lambda_.Runtime.PYTHON_3_11,
        handler="admin_delete.lambda_handler",
        code=lambda_.Code.from_asset("lambda"),
        environment={
            "USERS_TABLE": users_table.table_name,
            "WEB_PUSH_TABLE": web_push_table.table_name,
            "ENVIRONMENT": env_config.name,
            "DEBUG": str(env_config.debug_mode).lower(),
        },
        layers=[layer],
        role=role,
    )
    users_table.grant_write_data(fn)
    web_push_table.grant_write_data(fn)
    return fn


def create_admin_authorizer_lambda(
    scope: Construct, role, env_config: EnvironmentConfig
) -> lambda_.Function:
    fn = lambda_.Function(
        scope,
        "AdminAuthorizerLambda",
        function_name=f"{env_config.resource_name_prefix}-admin-authorizer",
        runtime=lambda_.Runtime.PYTHON_3_11,
        handler="admin_auth.lambda_handler",
        code=lambda_.Code.from_asset("lambda"),
        environment={
            "ADMIN_SECRET_PARAM": env_config.admin_secret_param,
            "ENVIRONMENT": env_config.name,
        },
        role=role,
    )
    secret_arn = (
        f"arn:aws:ssm:{env_config.region}:{env_config.account}:parameter"
        f"{env_config.admin_secret_param}"
    )
    fn.add_to_role_policy(
        iam.PolicyStatement(
            actions=["ssm:GetParameter"],
            resources=[secret_arn],
            effect=iam.Effect.ALLOW,
        )
    )

    return fn
