import json
import os
import importlib
import sys

import boto3
from moto import mock_aws

ROOT = os.path.dirname(os.path.dirname(__file__))
LAMBDA_DIR = os.path.join(ROOT, "lambda")
sys.path.insert(0, LAMBDA_DIR)


def reload_module(name):
    if name in sys.modules:
        return importlib.reload(sys.modules[name])
    return importlib.import_module(name)


@mock_aws
def test_admin_stats_counts():
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
        AttributeDefinitions=[{"AttributeName": "subscription_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    users_table = boto3.resource("dynamodb", region_name="us-east-1").Table("Users")
    users_table.put_item(Item={"user_id": "a"})
    users_table.put_item(Item={"user_id": "b"})
    web_table = boto3.resource("dynamodb", region_name="us-east-1").Table("WebPush")
    web_table.put_item(Item={"subscription_id": "x"})

    os.environ["USERS_TABLE"] = "Users"
    os.environ["WEB_PUSH_TABLE"] = "WebPush"

    mod = reload_module("admin_stats")
    result = mod.lambda_handler({}, None)
    body = json.loads(result["body"])
    assert body["users"] == 2
    assert body["web_push"] == 1


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
        AttributeDefinitions=[{"AttributeName": "subscription_id", "AttributeType": "S"}],
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

