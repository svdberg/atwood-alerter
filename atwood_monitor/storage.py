# storage.py

from aws_cdk import RemovalPolicy
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_sns as sns
from constructs import Construct


def create_tables(scope: Construct):
    posts_table = dynamodb.Table(
        scope, "PostsTable",
        partition_key=dynamodb.Attribute(name="post_id", type=dynamodb.AttributeType.STRING),
        billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
        table_name="Posts"
    )

    users_table = dynamodb.Table(
        scope, "UsersTable",
        partition_key=dynamodb.Attribute(name="user_id", type=dynamodb.AttributeType.STRING),
        billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
        table_name="Users"
    )

    web_push_table = dynamodb.Table(
        scope, "WebPushSubscriptionsTable",
        partition_key=dynamodb.Attribute(name="subscription_id", type=dynamodb.AttributeType.STRING),
        billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
        removal_policy=RemovalPolicy.DESTROY,
        time_to_live_attribute="ttl"
    )

    notify_topic = sns.Topic(
        scope, "NotifyTopic",
        display_name="Atwood Blog Notifications"
    )

    web_notify_topic = sns.Topic(
        scope, "WebNotifyTopic"
    )

    return posts_table, users_table, web_push_table, notify_topic, web_notify_topic
