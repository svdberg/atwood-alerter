import importlib
import json
import os
import sys

import boto3
import pytest
from moto import mock_aws
from pywebpush import WebPushException

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "lambda", "lambda-docker")
)

U = "https://atwoodknives.blogspot.com/p"
I = "https://img/x.jpg"


def _load(monkeypatch):
    monkeypatch.setenv("VAPID_PRIVATE_KEY", "dummy")
    monkeypatch.setenv("WEB_PUSH_TABLE", "WebPushTest")
    ddb = boto3.resource("dynamodb")
    table = ddb.create_table(
        TableName="WebPushTest",
        KeySchema=[{"AttributeName": "subscription_id", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "subscription_id", "AttributeType": "S"}
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    for n in ("a", "b"):
        table.put_item(
            Item={
                "subscription_id": n,
                "subscription": json.dumps({"endpoint": f"https://push.example/{n}"}),
            }
        )
    sys.modules.pop("web_push_lambda", None)
    mod = importlib.import_module("web_push_lambda")
    monkeypatch.setattr(mod.cloudwatch, "put_metric_data", lambda **kw: None)
    return mod, table


def _event(msg):
    return {"Records": [{"Sns": {"Message": json.dumps(msg)}}]}


@mock_aws
def test_build_push_data(monkeypatch):
    mod, _ = _load(monkeypatch)
    msg = {"title": "New Atwood release", "body": "B", "url": U, "image_url": I}
    assert json.loads(mod.build_push_data(msg)) == msg
    assert json.loads(mod.build_push_data({})) == {
        "title": "Atwood Blog",
        "body": "New post!",
        "url": "https://atwoodknives.blogspot.com/",
        "image_url": None,
    }


@mock_aws
def test_handler_sends_high_urgency_with_ttl(monkeypatch):
    mod, _ = _load(monkeypatch)
    calls = []
    monkeypatch.setattr(mod, "webpush", lambda **kw: calls.append(kw))
    msg = {"title": "T", "body": "B", "url": U, "image_url": I}
    mod.lambda_handler(_event(msg), None)
    assert len(calls) == 2
    for kw in calls:
        assert kw["ttl"] == 600
        assert kw["headers"]["Urgency"] == "high"
        assert json.loads(kw["data"])["image_url"] == I
    assert id(calls[0]["headers"]) != id(calls[1]["headers"])


@mock_aws
def test_handler_deletes_gone_subscription(monkeypatch):
    mod, table = _load(monkeypatch)

    class Resp:
        status_code = 410

    def fake(**kw):
        if kw["subscription_info"]["endpoint"].endswith("/a"):
            raise WebPushException("gone", response=Resp())

    monkeypatch.setattr(mod, "webpush", fake)
    mod.lambda_handler(_event({"title": "T", "url": U}), None)
    ids = {i["subscription_id"] for i in table.scan()["Items"]}
    assert ids == {"b"}
