import importlib
import json
import os
import sys

import boto3
import pytest
import requests
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
    for n in ("a", "b", "c"):
        table.put_item(
            Item={
                "subscription_id": n,
                "subscription": json.dumps({"endpoint": f"https://push.example/{n}"}),
            }
        )
    sys.modules.pop("web_push_lambda", None)
    mod = importlib.import_module("web_push_lambda")
    metrics = []
    monkeypatch.setattr(
        mod.cloudwatch,
        "put_metric_data",
        lambda **kw: metrics.extend(m["MetricName"] for m in kw["MetricData"]),
    )
    mod.metrics = metrics
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
    assert len(calls) == 3
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
    assert ids == {"b", "c"}


def _load_without_key(monkeypatch, environment="production"):
    # Like _load(), but leaves VAPID_PRIVATE_KEY unset after _load sets it.
    monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.setenv("WEB_PUSH_TABLE", "WebPushTest")
    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)
    ddb = boto3.resource("dynamodb")
    table = ddb.create_table(
        TableName="WebPushTest",
        KeySchema=[{"AttributeName": "subscription_id", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "subscription_id", "AttributeType": "S"}
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    table.put_item(
        Item={
            "subscription_id": "a",
            "subscription": json.dumps({"endpoint": "https://push.example/a"}),
        }
    )
    sys.modules.pop("web_push_lambda", None)
    mod = importlib.import_module("web_push_lambda")
    monkeypatch.setattr(mod.cloudwatch, "put_metric_data", lambda **kw: None)
    return mod


def _count_ssm(monkeypatch, mod):
    names = []
    real = mod.ssm.get_parameter

    def wrapper(**kw):
        names.append(kw["Name"])
        return real(**kw)

    monkeypatch.setattr(mod.ssm, "get_parameter", wrapper)
    return names


@mock_aws
def test_import_makes_no_ssm_call(monkeypatch):
    # No env key and no SSM parameter: import must still succeed.
    mod = _load_without_key(monkeypatch)
    assert mod._vapid_private_key is None


@mock_aws
def test_staging_key_fetched_from_ssm_and_cached(monkeypatch):
    mod = _load_without_key(monkeypatch, "staging")
    boto3.client("ssm").put_parameter(
        Name="/atwood/staging/vapid_private_key",
        Value="staging-secret",
        Type="SecureString",
    )
    names = _count_ssm(monkeypatch, mod)
    calls = []
    monkeypatch.setattr(mod, "webpush", lambda **kw: calls.append(kw))
    mod.lambda_handler(_event({"title": "T", "url": U}), None)
    mod.lambda_handler(_event({"title": "T", "url": U}), None)
    assert [kw["vapid_private_key"] for kw in calls] == ["staging-secret"] * 2
    assert names == ["/atwood/staging/vapid_private_key"]


@mock_aws
def test_env_key_used_without_ssm(monkeypatch):
    mod, _ = _load(monkeypatch)  # sets VAPID_PRIVATE_KEY=dummy
    names = _count_ssm(monkeypatch, mod)
    calls = []
    monkeypatch.setattr(mod, "webpush", lambda **kw: calls.append(kw))
    mod.lambda_handler(_event({"title": "T", "url": U}), None)
    assert calls and all(kw["vapid_private_key"] == "dummy" for kw in calls)
    assert names == []


@mock_aws
def test_production_key_path(monkeypatch):
    mod = _load_without_key(monkeypatch, "production")
    boto3.client("ssm").put_parameter(
        Name="/atwood/vapid_private_key", Value="prod-secret", Type="SecureString"
    )
    names = _count_ssm(monkeypatch, mod)
    assert mod.get_vapid_private_key() == "prod-secret"
    assert names == ["/atwood/vapid_private_key"]


class FakeResp:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


def _fail_on(mod, monkeypatch, failures):
    """failures: {endpoint suffix: exception to raise}; others succeed."""
    calls = []

    def fake(**kw):
        calls.append(kw["subscription_info"]["endpoint"])
        for suffix, exc in failures.items():
            if kw["subscription_info"]["endpoint"].endswith("/" + suffix):
                raise exc

    monkeypatch.setattr(mod, "webpush", fake)
    return calls


def _ids(table):
    return {i["subscription_id"] for i in table.scan()["Items"]}


def _exc(status, text=""):
    return WebPushException("fail", response=FakeResp(status, text))


VAPID_MISMATCH = '{"reason":"VapidPkHashMismatch"}'


@pytest.mark.parametrize("status", [404, 410])
@pytest.mark.parametrize("body", ["", None, '{"reason":"Whatever"}'])
def test_classify_gone(status, body):
    assert classify(status, body)[0] == "delete"


@pytest.mark.parametrize("status", [400, 403])
@pytest.mark.parametrize(
    "reason",
    ["VapidPkHashMismatch", "BadDeviceToken", "Unregistered", "ExpiredSubscription"],
)
def test_classify_dead_reasons(status, reason):
    body = json.dumps({"reason": reason})
    assert classify(status, body) == ("delete_if_confirmed", reason)


@pytest.mark.parametrize("status", [400, 403])
@pytest.mark.parametrize(
    "body",
    [
        '{"error":{"status":"NOT_FOUND","details":[{"errorCode":"UNREGISTERED"}]}}',
        '{"error":{"status":"INVALID_REGISTRATION"}}',
    ],
)
def test_classify_fcm(status, body):
    assert classify(status, body)[0] == "delete_if_confirmed"


@pytest.mark.parametrize("status", [400, 403])
@pytest.mark.parametrize(
    "body",
    [
        '{"reason":"BadJwtToken"}',
        '{"reason":"InvalidProviderToken"}',
        '{"reason":"ExpiredProviderToken"}',
        '{"reason":"SomethingNew"}',
        "",
        None,
        "Bad Request",
        "[1, 2]",
    ],
)
def test_classify_keep_400_403(status, body):
    assert classify(status, body)[0] == "keep"


@pytest.mark.parametrize("status", [None, 401, 413, 429, 500, 502, 503])
def test_classify_keep_other_statuses(status):
    assert classify(status, '{"reason":"Unregistered"}')[0] == "keep"


@pytest.mark.parametrize(
    "body,expected",
    [
        ('{"reason":"R","message":"m"}', "R"),
        ('{"error":{"details":[{"x":1},{"errorCode":"E"}],"status":"S"}}', "E"),
        ('{"error":{"status":"S"}}', "S"),
        ('{"error":"plain"}', "plain"),
        ('{"message":"m"}', "m"),
        ("{}", None),
        ("nope", None),
        ("", None),
        (None, None),
    ],
)
def test_extract_reason(body, expected):
    from web_push_lambda import extract_reason

    assert extract_reason(body) == expected


def classify(status, body):
    from web_push_lambda import classify_failure

    return classify_failure(status, body)


@mock_aws
def test_handler_deletes_confirmed_dead_when_one_succeeds(monkeypatch):
    mod, table = _load(monkeypatch)
    _fail_on(mod, monkeypatch, {"a": _exc(400, VAPID_MISMATCH)})
    mod.lambda_handler(_event({"title": "T", "url": U}), None)
    assert _ids(table) == {"b", "c"}
    assert mod.metrics.count("PushSubscriptionDeleted") == 1


@mock_aws
def test_handler_keeps_all_when_none_succeed(monkeypatch, capsys):
    mod, table = _load(monkeypatch)
    err = {n: _exc(400, VAPID_MISMATCH) for n in "abc"}
    _fail_on(mod, monkeypatch, err)
    mod.lambda_handler(_event({"title": "T", "url": U}), None)
    assert _ids(table) == {"a", "b", "c"}
    assert "PushSubscriptionDeleted" not in mod.metrics
    assert "Skipping deletion of 3 subscriptions" in capsys.readouterr().out


@mock_aws
def test_handler_gone_deleted_server_error_kept(monkeypatch):
    mod, table = _load(monkeypatch)
    _fail_on(mod, monkeypatch, {"a": _exc(410), "b": _exc(500)})
    mod.lambda_handler(_event({"title": "T", "url": U}), None)
    assert _ids(table) == {"b", "c"}


@mock_aws
def test_handler_continues_after_timeout(monkeypatch):
    mod, table = _load(monkeypatch)
    calls = _fail_on(mod, monkeypatch, {"a": requests.exceptions.Timeout("slow")})
    mod.lambda_handler(_event({"title": "T", "url": U}), None)
    assert len(calls) == 3
    assert _ids(table) == {"a", "b", "c"}
    assert mod.metrics.count("PushFailure") == 1


@mock_aws
def test_handler_keeps_on_config_error(monkeypatch):
    mod, table = _load(monkeypatch)
    _fail_on(mod, monkeypatch, {"a": _exc(400, '{"reason":"BadJwtToken"}')})
    mod.lambda_handler(_event({"title": "T", "url": U}), None)
    assert _ids(table) == {"a", "b", "c"}
    assert "PushSubscriptionDeleted" not in mod.metrics


@mock_aws
def test_handler_logs_id_status_reason(monkeypatch, capsys):
    mod, _ = _load(monkeypatch)
    _fail_on(mod, monkeypatch, {"a": _exc(400, VAPID_MISMATCH)})
    mod.lambda_handler(_event({"title": "T", "url": U}), None)
    line = next(
        ln for ln in capsys.readouterr().out.splitlines() if "Push failed" in ln
    )
    assert "a:" in line and "400" in line and "VapidPkHashMismatch" in line


@mock_aws
def test_handler_response_none_keeps_subscription(monkeypatch):
    mod, table = _load(monkeypatch)
    _fail_on(mod, monkeypatch, {"a": WebPushException("boom", response=None)})
    mod.lambda_handler(_event({"title": "T", "url": U}), None)
    assert _ids(table) == {"a", "b", "c"}
