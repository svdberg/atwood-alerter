# storage.py

from aws_cdk import (
    RemovalPolicy,
    aws_dynamodb as dynamodb,
    aws_sns as sns,
)
from constructs import Construct

from .environments import EnvironmentConfig


def create_tables(scope: Construct, env_config: EnvironmentConfig):
    """Create DynamoDB tables and SNS topics with environment-specific naming."""

    posts_table = dynamodb.Table(
        scope,
        "PostsTable",
        partition_key=dynamodb.Attribute(
            name="post_id", type=dynamodb.AttributeType.STRING
        ),
        billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
        table_name=f"{env_config.resource_name_prefix}-posts",
        removal_policy=(
            RemovalPolicy.DESTROY
            if env_config.name != "production"
            else RemovalPolicy.RETAIN
        ),
    )

    users_table = dynamodb.Table(
        scope,
        "UsersTable",
        partition_key=dynamodb.Attribute(
            name="user_id", type=dynamodb.AttributeType.STRING
        ),
        billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
        table_name=f"{env_config.resource_name_prefix}-users",
        removal_policy=(
            RemovalPolicy.DESTROY
            if env_config.name != "production"
            else RemovalPolicy.RETAIN
        ),
    )

    web_push_table = dynamodb.Table(
        scope,
        "WebPushSubscriptionsTable",
        partition_key=dynamodb.Attribute(
            name="subscription_id", type=dynamodb.AttributeType.STRING
        ),
        billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
        table_name=f"{env_config.resource_name_prefix}-web-push-subscriptions",
        removal_policy=RemovalPolicy.DESTROY,
        time_to_live_attribute="ttl",
    )

    notify_topic = sns.Topic(
        scope,
        "NotifyTopic",
        display_name=f"Atwood Blog Notifications ({env_config.name.title()})",
        topic_name=f"{env_config.resource_name_prefix}-notifications",
    )

    web_notify_topic = sns.Topic(
        scope,
        "WebNotifyTopic",
        display_name=f"Atwood Web Push Notifications ({env_config.name.title()})",
        topic_name=f"{env_config.resource_name_prefix}-web-notifications",
    )

    return posts_table, users_table, web_push_table, notify_topic, web_notify_topic
