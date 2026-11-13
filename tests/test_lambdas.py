import hashlib
import importlib
import json
import os
import sys

import boto3
import pytest
from moto import mock_aws

# Add lambda directory to path
ROOT = os.path.dirname(os.path.dirname(__file__))
LAMBDA_DIR = os.path.join(ROOT, "lambda")
sys.path.insert(0, LAMBDA_DIR)

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")


def reload_module(name):
    if name in sys.modules:
        return importlib.reload(sys.modules[name])
    return importlib.import_module(name)


CORS_JSON_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "*",
    "Content-Type": "application/json",
}
INVALID_EMAIL = {"error": "Please enter a valid email address."}


def _subscribe_setup():
    ddb = boto3.client("dynamodb", region_name="us-east-1")
    ddb.create_table(
        TableName="Users",
        KeySchema=[{"AttributeName": "user_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "user_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    sns = boto3.client("sns", region_name="us-east-1")
    topic_arn = sns.create_topic(Name="Notify")["TopicArn"]

    os.environ["USERS_TABLE"] = "Users"
    os.environ["NOTIFY_TOPIC_ARN"] = topic_arn
    return reload_module("subscribe_lambda"), sns, topic_arn


def _assert_cors_json(result):
    for key, value in CORS_JSON_HEADERS.items():
        assert result["headers"][key] == value


@mock_aws
def test_subscribe_lambda_valid_email():
    subscribe_lambda, sns, topic_arn = _subscribe_setup()

    event = {"body": json.dumps({"email": "foo@example.com"})}
    result = subscribe_lambda.lambda_handler(event, None)

    assert result["statusCode"] == 200
    assert json.loads(result["body"]) == {
        "message": "Subscription requested. Check your email to confirm."
    }
    _assert_cors_json(result)
    table = boto3.resource("dynamodb", region_name="us-east-1").Table("Users")
    assert "Item" in table.get_item(Key={"user_id": "foo@example.com"})
    subs = sns.list_subscriptions_by_topic(TopicArn=topic_arn)["Subscriptions"]
    assert len(subs) == 1


@mock_aws
def test_subscribe_lambda_invalid_email():
    subscribe_lambda, _, _ = _subscribe_setup()

    event = {"body": json.dumps({"email": "bademail"})}
    result = subscribe_lambda.lambda_handler(event, None)

    assert result["statusCode"] == 400
    assert json.loads(result["body"]) == INVALID_EMAIL
    _assert_cors_json(result)


@mock_aws
@pytest.mark.parametrize(
    "payload", [{}, {"email": ""}, {"email": 123}, {"email": None}]
)
def test_subscribe_lambda_bad_email_values(payload):
    subscribe_lambda, _, _ = _subscribe_setup()

    result = subscribe_lambda.lambda_handler({"body": json.dumps(payload)}, None)

    assert result["statusCode"] == 400
    assert json.loads(result["body"]) == INVALID_EMAIL
    _assert_cors_json(result)


@mock_aws
@pytest.mark.parametrize("event", [{}, {"body": None}, {"body": ""}])
def test_subscribe_lambda_missing_body(event, monkeypatch):
    subscribe_lambda, sns, topic_arn = _subscribe_setup()

    def boom(*args, **kwargs):
        raise AssertionError("AWS must not be called")

    monkeypatch.setattr(subscribe_lambda.table, "put_item", boom)
    monkeypatch.setattr(subscribe_lambda.sns, "subscribe", boom)

    result = subscribe_lambda.lambda_handler(event, None)

    assert result["statusCode"] == 400
    assert "error" in json.loads(result["body"])
    _assert_cors_json(result)


@mock_aws
@pytest.mark.parametrize("raw", ["not json", "[1,2]"])
def test_subscribe_lambda_malformed_body(raw):
    subscribe_lambda, _, _ = _subscribe_setup()

    result = subscribe_lambda.lambda_handler({"body": raw}, None)

    assert result["statusCode"] == 400
    assert json.loads(result["body"]) == {"error": "Invalid request body."}
    _assert_cors_json(result)


@mock_aws
def test_subscribe_lambda_sns_failure_is_generic_and_logged(monkeypatch, capsys):
    subscribe_lambda, _, _ = _subscribe_setup()

    def boom(*args, **kwargs):
        raise Exception("internal-detail-xyz")

    monkeypatch.setattr(subscribe_lambda.sns, "subscribe", boom)

    result = subscribe_lambda.lambda_handler(
        {"body": json.dumps({"email": "foo@example.com"})}, None
    )

    assert result["statusCode"] == 500
    assert json.loads(result["body"]) == {
        "error": "Something went wrong. Please try again later."
    }
    assert "internal-detail-xyz" not in result["body"]
    _assert_cors_json(result)
    out = capsys.readouterr().out
    assert "internal-detail-xyz" in out
    assert "foo@example.com" not in out


def test_json_response_helper():
    http_response = reload_module("http_response")

    result = http_response.json_response(418, {"a": 1})

    assert result["statusCode"] == 418
    assert result["headers"] == CORS_JSON_HEADERS
    assert result["body"] == '{"a": 1}'


@mock_aws
def test_subscribe_web_lambda_registers_subscription():
    ddb = boto3.client("dynamodb", region_name="us-east-1")
    ddb.create_table(
        TableName="WebPush",
        KeySchema=[{"AttributeName": "subscription_id", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "subscription_id", "AttributeType": "S"}
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    os.environ["WEB_PUSH_TABLE"] = "WebPush"

    subscribe_web_lambda = reload_module("subscribe_web_lambda")

    body = {"endpoint": "https://example.com/endpoint"}
    event = {"body": json.dumps(body)}
    result = subscribe_web_lambda.lambda_handler(event, None)

    assert result["statusCode"] == 200
    _assert_cors_json(result)
    sub_id = hashlib.sha256(json.dumps(body).encode()).hexdigest()
    table = boto3.resource("dynamodb", region_name="us-east-1").Table("WebPush")
    assert "Item" in table.get_item(Key={"subscription_id": sub_id})


@mock_aws
def test_subscribe_web_lambda_missing_endpoint():
    ddb = boto3.client("dynamodb", region_name="us-east-1")
    ddb.create_table(
        TableName="WebPush",
        KeySchema=[{"AttributeName": "subscription_id", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "subscription_id", "AttributeType": "S"}
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    os.environ["WEB_PUSH_TABLE"] = "WebPush"
    subscribe_web_lambda = reload_module("subscribe_web_lambda")

    result = subscribe_web_lambda.lambda_handler({"body": json.dumps({})}, None)

    assert result["statusCode"] == 400
    assert json.loads(result["body"]) == {"error": "Missing endpoint in subscription"}
    _assert_cors_json(result)


@mock_aws
def test_status_lambda_returns_metadata():
    ddb = boto3.client("dynamodb", region_name="us-east-1")
    ddb.create_table(
        TableName="Posts",
        KeySchema=[{"AttributeName": "post_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "post_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )

    os.environ["POSTS_TABLE"] = "Posts"

    table = boto3.resource("dynamodb", region_name="us-east-1").Table("Posts")
    meta = {
        "post_id": "__meta__",
        "last_run_time": "123",
        "last_seen_post": {"title": "My Post"},
    }
    table.put_item(Item=meta)

    status_lambda = reload_module("status_lambda")

    result = status_lambda.lambda_handler({}, None)

    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["last_run_time"] == "123"
    assert body["last_seen_post"]["title"] == "My Post"


@mock_aws
def test_extract_image_from_entry():
    ddb = boto3.client("dynamodb", region_name="us-east-1")
    ddb.create_table(
        TableName="Posts",
        KeySchema=[{"AttributeName": "post_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "post_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    ddb.create_table(
        TableName="Users",
        KeySchema=[{"AttributeName": "user_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "user_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    sns = boto3.client("sns", region_name="us-east-1")
    topic_arn = sns.create_topic(Name="Notify")["TopicArn"]

    os.environ["POSTS_TABLE"] = "Posts"
    os.environ["USERS_TABLE"] = "Users"
    os.environ["NOTIFY_TOPIC_ARN"] = topic_arn

    reload_module("dynamo")
    lambda_function = reload_module("lambda_function")

    class Entry(dict):
        __getattr__ = dict.get

    entry = Entry(media_content=[{"url": "http://img.test/img.jpg"}])
    assert lambda_function.extract_image_from_entry(entry) == "http://img.test/img.jpg"


def _scraper_env():
    ddb = boto3.client("dynamodb", region_name="us-east-1")
    ddb.create_table(
        TableName="Posts",
        KeySchema=[{"AttributeName": "post_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "post_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    sns = boto3.client("sns", region_name="us-east-1")
    topic_arn = sns.create_topic(Name="Notify")["TopicArn"]
    sns.subscribe(TopicArn=topic_arn, Protocol="email", Endpoint="a@example.com")
    sns.subscribe(TopicArn=topic_arn, Protocol="email", Endpoint="b@example.com")
    os.environ["POSTS_TABLE"] = "Posts"
    os.environ["NOTIFY_TOPIC_ARN"] = topic_arn
    reload_module("dynamo")
    mod = reload_module("lambda_function")
    return mod, boto3.resource("dynamodb", region_name="us-east-1").Table("Posts")


POST = {"title": "T", "url": "https://example.com/p"}


@mock_aws
def test_notify_subscribers_records_stats():
    from datetime import datetime, timezone

    mod, posts = _scraper_env()
    # Pending subscriptions and the lambda subscription must not be counted.
    real = mod.sns.list_subscriptions_by_topic

    def with_pending(**kwargs):
        resp = real(**kwargs)
        resp["Subscriptions"].append(
            {"Protocol": "email", "SubscriptionArn": "PendingConfirmation"}
        )
        resp["Subscriptions"].append(
            {"Protocol": "lambda", "SubscriptionArn": "arn:aws:sns:x:1:t:abc"}
        )
        return resp

    mod.sns.list_subscriptions_by_topic = with_pending
    try:
        mod.notify_subscribers(POST)
        mod.notify_subscribers(POST)
    finally:
        mod.sns.list_subscriptions_by_topic = real
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    item = posts.get_item(Key={"post_id": f"__stats__#{month}"})["Item"]
    assert item["posts_announced"] == 2
    assert item["email_recipients"] == 4
    assert item["last_sent"]


@mock_aws
def test_notify_subscribers_publish_failure_writes_nothing():
    mod, posts = _scraper_env()

    def boom(**kwargs):
        raise RuntimeError("publish failed")

    real = mod.sns.publish
    mod.sns.publish = boom
    try:
        mod.notify_subscribers(POST)
    finally:
        mod.sns.publish = real
    assert posts.scan()["Items"] == []


@mock_aws
def test_notify_subscribers_swallows_stats_failure(monkeypatch):
    mod, posts = _scraper_env()
    published = []
    real = mod.sns.publish

    def spy(**kwargs):
        published.append(kwargs)
        return real(**kwargs)

    def boom(*args, **kwargs):
        raise RuntimeError("ddb down")

    mod.sns.publish = spy
    monkeypatch.setattr(mod, "record_notification", boom)
    try:
        mod.notify_subscribers(POST)
    finally:
        mod.sns.publish = real
    assert len(published) == 1


@mock_aws
def test_record_notification_increments_month():
    from datetime import datetime, timezone

    _, posts = _scraper_env()
    dynamo = sys.modules["dynamo"]
    dynamo.record_notification(3, datetime(2026, 11, 1, tzinfo=timezone.utc))
    dynamo.record_notification(2, datetime(2026, 11, 30, tzinfo=timezone.utc))
    item = posts.get_item(Key={"post_id": "__stats__#2026-11"})["Item"]
    assert item["posts_announced"] == 2
    assert item["email_recipients"] == 5
    assert item["last_sent"].startswith("2026-11-30")
