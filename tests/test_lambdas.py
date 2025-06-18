import hashlib
import importlib
import json
import os
import sys

import boto3
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


@mock_aws
def test_subscribe_lambda_valid_email():
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

    subscribe_lambda = reload_module("subscribe_lambda")

    event = {"body": json.dumps({"email": "foo@example.com"})}
    result = subscribe_lambda.lambda_handler(event, None)

    assert result["statusCode"] == 200
    table = boto3.resource("dynamodb", region_name="us-east-1").Table("Users")
    assert "Item" in table.get_item(Key={"user_id": "foo@example.com"})
    subs = sns.list_subscriptions_by_topic(TopicArn=topic_arn)["Subscriptions"]
    assert len(subs) == 1


@mock_aws
def test_subscribe_lambda_invalid_email():
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

    subscribe_lambda = reload_module("subscribe_lambda")

    event = {"body": json.dumps({"email": "bademail"})}
    result = subscribe_lambda.lambda_handler(event, None)

    assert result["statusCode"] == 400


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
    sub_id = hashlib.sha256(json.dumps(body).encode()).hexdigest()
    table = boto3.resource("dynamodb", region_name="us-east-1").Table("WebPush")
    assert "Item" in table.get_item(Key={"subscription_id": sub_id})


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
