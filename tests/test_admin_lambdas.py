import importlib
import json
import os
import sys
from datetime import datetime, timezone

import boto3
from moto import mock_aws

ROOT = os.path.dirname(os.path.dirname(__file__))
LAMBDA_DIR = os.path.join(ROOT, "lambda")
sys.path.insert(0, LAMBDA_DIR)


def reload_module(name):
    if name in sys.modules:
        return importlib.reload(sys.modules[name])
    return importlib.import_module(name)


NOW = datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)


def _setup_stats_env():
    """Create tables, a topic and env vars. Returns (topic_arn, posts_table)."""
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    ddb = boto3.client("dynamodb", region_name="us-east-1")
    ddb.create_table(
        TableName="Users",
        KeySchema=[{"AttributeName": "user_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "user_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    ddb.create_table(
        TableName="WebPush",
        KeySchema=[{"AttributeName": "subscription_id", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "subscription_id", "AttributeType": "S"}
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    ddb.create_table(
        TableName="Posts",
        KeySchema=[{"AttributeName": "post_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "post_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    res = boto3.resource("dynamodb", region_name="us-east-1")
    res.Table("Users").put_item(Item={"user_id": "a"})
    res.Table("Users").put_item(Item={"user_id": "b"})
    res.Table("WebPush").put_item(Item={"subscription_id": "x"})
    sns = boto3.client("sns", region_name="us-east-1")
    topic_arn = sns.create_topic(Name="Notify")["TopicArn"]
    sns.subscribe(TopicArn=topic_arn, Protocol="email", Endpoint="a@example.com")
    sns.subscribe(TopicArn=topic_arn, Protocol="email", Endpoint="b@example.com")
    os.environ["USERS_TABLE"] = "Users"
    os.environ["WEB_PUSH_TABLE"] = "WebPush"
    os.environ["POSTS_TABLE"] = "Posts"
    os.environ["NOTIFY_TOPIC_ARN"] = topic_arn
    os.environ["ENVIRONMENT"] = "staging"
    return topic_arn, res.Table("Posts")


def _put_metric(name, value, ts, env="Staging"):
    boto3.client("cloudwatch", region_name="us-east-1").put_metric_data(
        Namespace="WebPushNotifications",
        MetricData=[
            {
                "MetricName": name,
                "Dimensions": [{"Name": "Environment", "Value": env}],
                "Timestamp": ts,
                "Value": value,
                "Unit": "Count",
            }
        ],
    )


@mock_aws
def test_admin_stats_counts():
    _setup_stats_env()
    mod = reload_module("admin_stats")
    result = mod.lambda_handler({}, None)
    body = json.loads(result["body"])
    assert body["users"] == 2
    assert body["web_push"] == 1


@mock_aws
def test_build_stats_subscribers_from_sns(monkeypatch):
    topic_arn, _ = _setup_stats_env()
    boto3.client("sns", region_name="us-east-1").subscribe(
        TopicArn=topic_arn,
        Protocol="lambda",
        Endpoint="arn:aws:lambda:us-east-1:123456789012:function:f",
    )
    mod = reload_module("admin_stats")
    stats = mod.build_stats(NOW)
    assert stats["subscribers"] == {
        "email_confirmed": 2,
        "email_pending": 0,
        "web_push": 1,
    }

    real = mod.sns.list_subscriptions_by_topic

    def with_pending(**kwargs):
        resp = real(**kwargs)
        resp["Subscriptions"].append(
            {"Protocol": "email", "SubscriptionArn": "PendingConfirmation"}
        )
        return resp

    monkeypatch.setattr(mod.sns, "list_subscriptions_by_topic", with_pending)
    subs = mod.build_stats(NOW)["subscribers"]
    assert subs["email_confirmed"] == 2
    assert subs["email_pending"] == 1


@mock_aws
def test_build_stats_monthly_and_totals():
    _, posts = _setup_stats_env()
    posts.put_item(
        Item={
            "post_id": "__stats__#2026-11",
            "posts_announced": 2,
            "email_recipients": 20,
            "last_sent": "2026-11-10T18:07:00+00:00",
        }
    )
    posts.put_item(
        Item={
            "post_id": "__stats__#2026-01",
            "posts_announced": 1,
            "email_recipients": 8,
            "last_sent": "2026-01-05T08:00:00+00:00",
        }
    )
    # Out of the 12 month window: ignored.
    posts.put_item(
        Item={
            "post_id": "__stats__#2025-10",
            "posts_announced": 9,
            "email_recipients": 99,
            "last_sent": "2025-10-01T00:00:00+00:00",
        }
    )
    _put_metric("PushSuccess", 5, datetime(2026, 11, 3, 12, tzinfo=timezone.utc))
    _put_metric("PushSuccess", 4, datetime(2026, 11, 9, 12, tzinfo=timezone.utc))
    _put_metric("PushSuccess", 3, datetime(2026, 1, 15, 12, tzinfo=timezone.utc))
    _put_metric("PushFailure", 1, datetime(2026, 11, 9, 12, tzinfo=timezone.utc))
    _put_metric(
        "PushSuccess", 100, datetime(2026, 11, 9, 12, tzinfo=timezone.utc), "Production"
    )

    mod = reload_module("admin_stats")
    stats = mod.build_stats(NOW)
    monthly = stats["monthly"]
    assert len(monthly) == 12
    assert monthly[0]["month"] == "2025-12"
    assert monthly[-1]["month"] == "2026-11"
    by_month = {m["month"]: m for m in monthly}
    assert by_month["2026-11"] == {
        "month": "2026-11",
        "posts_announced": 2,
        "email_recipients": 20,
        "push_success": 9,
        "push_failure": 1,
    }
    assert by_month["2026-01"]["push_success"] == 3
    assert by_month["2026-03"] == {
        "month": "2026-03",
        "posts_announced": 0,
        "email_recipients": 0,
        "push_success": 0,
        "push_failure": 0,
    }
    assert stats["notifications"] == {
        "posts_announced": 3,
        "email_recipients": 28,
        "push_success": 12,
        "push_failure": 1,
        "last_sent": "2026-11-10T18:07:00+00:00",
    }
    json.dumps(stats)


@mock_aws
def test_build_stats_no_stats_items_last_sent_null():
    _setup_stats_env()
    mod = reload_module("admin_stats")
    stats = mod.build_stats(NOW)
    assert stats["notifications"]["last_sent"] is None
    assert stats["notifications"]["posts_announced"] == 0


@mock_aws
def test_build_stats_sns_failure_gives_nulls(monkeypatch):
    _setup_stats_env()
    mod = reload_module("admin_stats")

    def boom(**kwargs):
        raise RuntimeError("sns down")

    monkeypatch.setattr(mod.sns, "list_subscriptions_by_topic", boom)
    result = mod.lambda_handler({}, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["subscribers"]["email_confirmed"] is None
    assert body["subscribers"]["email_pending"] is None
    assert body["subscribers"]["web_push"] == 1
    assert body["monthly"][0]["push_success"] == 0


@mock_aws
def test_build_stats_cloudwatch_failure_gives_nulls(monkeypatch):
    _setup_stats_env()
    mod = reload_module("admin_stats")

    def boom(**kwargs):
        raise RuntimeError("cloudwatch down")

    monkeypatch.setattr(mod.cloudwatch, "get_metric_statistics", boom)
    result = mod.lambda_handler({}, None)
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["notifications"]["push_success"] is None
    assert body["notifications"]["push_failure"] is None
    assert all(m["push_success"] is None for m in body["monthly"])
    assert body["subscribers"]["email_confirmed"] == 2


@mock_aws
def test_build_stats_counts_across_scan_pages(monkeypatch):
    _setup_stats_env()
    mod = reload_module("admin_stats")
    real_scan = mod.users_table.scan

    def paged(**kwargs):
        if "ExclusiveStartKey" not in kwargs:
            resp = real_scan(Select="COUNT", Limit=1)
            resp["LastEvaluatedKey"] = {"user_id": "a"}
            return resp
        return real_scan(Select="COUNT", ExclusiveStartKey=kwargs["ExclusiveStartKey"])

    monkeypatch.setattr(mod.users_table, "scan", paged)
    assert mod.build_stats(NOW)["users"] == 2


@mock_aws
def test_admin_delete_user():
    ddb = boto3.client("dynamodb", region_name="us-east-1")
    ddb.create_table(
        TableName="Users",
        KeySchema=[{"AttributeName": "user_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "user_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    ddb.create_table(
        TableName="WebPush",
        KeySchema=[{"AttributeName": "subscription_id", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "subscription_id", "AttributeType": "S"}
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    table = boto3.resource("dynamodb", region_name="us-east-1").Table("Users")
    table.put_item(Item={"user_id": "a"})

    os.environ["USERS_TABLE"] = "Users"
    os.environ["WEB_PUSH_TABLE"] = "WebPush"

    mod = reload_module("admin_delete")
    event = {"body": json.dumps({"email": "a"})}
    result = mod.lambda_handler(event, None)
    assert result["statusCode"] == 200
    assert "Item" not in table.get_item(Key={"user_id": "a"})
