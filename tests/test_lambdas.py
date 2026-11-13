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


def _capture_publish(mod):
    published = []
    real = mod.sns.publish

    def spy(**kwargs):
        published.append(kwargs)
        return real(**kwargs)

    mod.sns.publish = spy
    return published, real


@mock_aws
def test_notify_subscribers_publishes_per_protocol_message():
    mod, _ = _scraper_env()
    published, real = _capture_publish(mod)
    post = {
        "title": "Spring drop",
        "url": "https://example.com/p",
        "sold": False,
        "image_url": "https://img/x.jpg",
    }
    try:
        mod.notify_subscribers(post)
    finally:
        mod.sns.publish = real
    assert len(published) == 1
    kwargs = published[0]
    assert kwargs["MessageStructure"] == "json"
    assert kwargs["TopicArn"] == os.environ["NOTIFY_TOPIC_ARN"]
    assert kwargs["Subject"] == "New Atwood release: Spring drop"
    message = json.loads(kwargs["Message"])
    assert set(message) == {"default", "email", "lambda"}
    assert all(isinstance(v, str) for v in message.values())
    expected = mod.build_push_payload(post)
    assert expected == {
        "title": "New Atwood release",
        "body": "Spring drop",
        "url": "https://example.com/p",
        "image_url": "https://img/x.jpg",
    }
    assert json.loads(message["lambda"]) == expected
    assert json.loads(message["default"]) == expected
    assert "Spring drop" in message["email"]
    assert post["url"] in message["email"].splitlines()
    try:
        json.loads(message["email"])
        raise AssertionError("email body must not be JSON")
    except ValueError:
        pass


@mock_aws
def test_push_payload_fields_and_sold():
    mod, _ = _scraper_env()
    post = {
        "title": "Spring drop",
        "url": "https://example.com/p",
        "sold": False,
        "image_url": "https://img/x.jpg",
    }
    assert mod.build_push_payload(post) == {
        "title": "New Atwood release",
        "body": "Spring drop",
        "url": "https://example.com/p",
        "image_url": "https://img/x.jpg",
    }
    sold = mod.build_push_payload({**post, "sold": True})
    assert sold["body"] == "Spring drop (already sold out)"


@mock_aws
@pytest.mark.parametrize(
    "value", [None, "", "http://img/x.jpg", "data:image/png;base64,AAAA", 5]
)
def test_push_payload_rejects_unsafe_image_url(value):
    mod, _ = _scraper_env()
    post = {"title": "T", "url": "https://example.com/p", "image_url": value}
    assert mod.build_push_payload(post)["image_url"] is None
    post.pop("image_url")
    assert mod.build_push_payload(post)["image_url"] is None


@mock_aws
def test_email_body_sold_status():
    mod, _ = _scraper_env()
    base = {"title": "T", "url": "https://example.com/p"}
    assert "Status: Available" in mod.build_email_body({**base, "sold": False})
    assert "Status: Available" in mod.build_email_body(base)
    assert "Status: Sold out" in mod.build_email_body({**base, "sold": True})


@mock_aws
def test_email_subject_truncates_long_title():
    mod, _ = _scraper_env()
    subject = mod.build_email_subject("a" * 200)
    assert len(subject) < 100
    assert subject.startswith("New Atwood release: ")
    assert subject.endswith("...")


@mock_aws
def test_email_subject_sanitises_non_ascii_and_newlines():
    mod, _ = _scraper_env()
    subject = mod.build_email_subject("Café\nPry-Bar 🔪\tdrop")
    assert subject == "New Atwood release: Cafe Pry-Bar drop"
    assert subject.isascii()
    assert all(0x20 <= ord(c) < 0x7F for c in subject)
    assert "  " not in subject


@mock_aws
def test_email_subject_fallback_when_empty():
    mod, _ = _scraper_env()
    for title in ("", "🔪🔪"):
        assert mod.build_email_subject(title) == "New Atwood release"


BLOGGER = "https://blogger.googleusercontent.com"


@pytest.mark.parametrize(
    "url,expected",
    [
        (None, None),
        ("", ""),
        (
            f"{BLOGGER}/img/b/R29v/AVvX/s72-c/PXL_1.jpg",
            f"{BLOGGER}/img/b/R29v/AVvX/s1200/PXL_1.jpg",
        ),
        (
            f"{BLOGGER}/img/b/R29v/AVvX/s1600/a.jpg",
            f"{BLOGGER}/img/b/R29v/AVvX/s1200/a.jpg",
        ),
        (
            f"{BLOGGER}/img/b/R29v/AVvX/w640-h480/a.jpg",
            f"{BLOGGER}/img/b/R29v/AVvX/s1200/a.jpg",
        ),
        (
            f"{BLOGGER}/img/b/R29v/AVvX/w640-h480-p-k-no-nu/a.jpg",
            f"{BLOGGER}/img/b/R29v/AVvX/s1200/a.jpg",
        ),
        (f"{BLOGGER}/img/a/AVvX=s72-c", f"{BLOGGER}/img/a/AVvX=s1200"),
        (f"{BLOGGER}/img/a/AVvX=w640-h480", f"{BLOGGER}/img/a/AVvX=s1200"),
        (
            "https://1.bp.blogspot.com/-abc/XYZ/s72-c/k.jpg",
            "https://1.bp.blogspot.com/-abc/XYZ/s1200/k.jpg",
        ),
        (
            "https://lh3.googleusercontent.com/a/s72-c/k.jpg",
            "https://lh3.googleusercontent.com/a/s1200/k.jpg",
        ),
        ("http://img.test/img.jpg", "http://img.test/img.jpg"),
        ("https://example.com/s72-c/a.jpg", "https://example.com/s72-c/a.jpg"),
        (
            "https://blogger.googleusercontent.com.evil.test/img/s72-c/a.jpg",
            "https://blogger.googleusercontent.com.evil.test/img/s72-c/a.jpg",
        ),
        (f"{BLOGGER}/img/b/X/Y/a.jpg", f"{BLOGGER}/img/b/X/Y/a.jpg"),
        (
            f"{BLOGGER}/img/b/X/Y/s1600/s72-c.jpg",
            f"{BLOGGER}/img/b/X/Y/s1200/s72-c.jpg",
        ),
        (f"{BLOGGER}/img/b/X/Y/s72-c.jpg", f"{BLOGGER}/img/b/X/Y/s72-c.jpg"),
        (f"{BLOGGER}/img/b/X/s72-c/a.jpg?x=1", f"{BLOGGER}/img/b/X/s1200/a.jpg?x=1"),
    ],
)
@mock_aws
def test_upscale_blogger_image_url(url, expected):
    mod, _ = _scraper_env()
    result = mod.upscale_blogger_image_url(url)
    assert result == expected
    assert mod.upscale_blogger_image_url(result) == result


@mock_aws
def test_extract_image_from_entry_upscales_blogger_urls():
    mod, _ = _scraper_env()

    class Entry(dict):
        __getattr__ = dict.get

    thumb = f"{BLOGGER}/img/b/R29v/AVvX/s72-c/PXL_1.jpg"
    full = f"{BLOGGER}/img/b/R29v/AVvX/s1200/PXL_1.jpg"
    assert mod.extract_image_from_entry(Entry(media_thumbnail=[{"url": thumb}])) == full
    summary = f'<div><img src="{thumb}"></div>'
    assert mod.extract_image_from_entry(Entry(summary=summary)) == full


# --- Recent releases / sold_at re-checks -----------------------------------

from datetime import datetime, timedelta, timezone  # noqa: E402
from email.utils import format_datetime  # noqa: E402

NOW = datetime(2026, 11, 13, 12, 0, 0, tzinfo=timezone.utc)
SOLD_HTML = "<div class='post-body'>Nice knife\nSold out</div>"
OPEN_HTML = "<div class='post-body'>Nice knife\nOrder now</div>"


class _Entry(dict):
    def __getattr__(self, name):
        return self[name]


def _entry(n, age):
    return _Entry(
        id=f"id{n}",
        title=f"Post {n}",
        link=f"https://blog.test/{n}",
        published=format_datetime(NOW - age),
    )


def _setup_recheck(monkeypatch, entries, sold_by_url, stored=None):
    mod, posts = _scraper_env()
    posts.put_item(Item={"post_id": "__meta__", "last_run_time": "x"})
    for e in entries if stored is None else stored:
        posts.put_item(
            Item={
                "post_id": e["id"],
                "title": e["title"],
                "url": e["link"],
                "sold": False,
            }
        )
    calls = []

    class Resp:
        def __init__(self, text):
            self.text = text

    def fake_get(url, timeout=None, **kw):
        assert timeout
        calls.append(url)
        result = sold_by_url.get(url, OPEN_HTML)
        if isinstance(result, Exception):
            raise result
        return Resp(result)

    class Feed:
        pass

    feed = Feed()
    feed.entries = entries
    monkeypatch.setattr(mod.feedparser, "parse", lambda url: feed)
    monkeypatch.setattr(mod.requests, "get", fake_get)
    monkeypatch.setattr(mod, "_utcnow", lambda: NOW)
    monkeypatch.setattr(mod, "extract_image_from_entry", lambda e: None)
    monkeypatch.setattr(mod, "notify_subscribers", lambda p: None)
    return mod, posts, calls


def _item(posts, n):
    return posts.get_item(Key={"post_id": f"id{n}"})["Item"]


@mock_aws
def test_fetch_sold_status_uses_timeout(monkeypatch):
    mod, _ = _scraper_env()
    seen = {}

    class Resp:
        text = SOLD_HTML

    def fake_get(url, timeout=None):
        seen["timeout"] = timeout
        return Resp()

    monkeypatch.setattr(mod.requests, "get", fake_get)
    assert mod.fetch_sold_status("https://x") is True
    assert seen["timeout"] == mod.REQUEST_TIMEOUT_S


@mock_aws
def test_recheck_marks_sold_with_sold_at(monkeypatch):
    entries = [_entry(1, timedelta(hours=1)), _entry(2, timedelta(days=2))]
    mod, posts, calls = _setup_recheck(
        monkeypatch, entries, {"https://blog.test/2": SOLD_HTML}
    )
    mod.lambda_handler({}, None)
    item = _item(posts, 2)
    assert item["sold"] is True
    assert item["sold_at"] == "2026-11-13T12:00:00Z"
    assert "sold_at" not in _item(posts, 1)

    # second run: sold post is never fetched again, sold_at unchanged
    calls.clear()
    monkeypatch.setattr(mod, "_utcnow", lambda: NOW + timedelta(hours=1))
    mod.lambda_handler({}, None)
    assert "https://blog.test/2" not in calls
    assert _item(posts, 2)["sold_at"] == "2026-11-13T12:00:00Z"


@mock_aws
def test_mark_sold_is_conditional():
    _, posts = _scraper_env()
    dynamo = sys.modules["dynamo"]
    posts.put_item(Item={"post_id": "p", "sold": False})
    assert dynamo.mark_sold("p", "2026-01-01T00:00:00Z") is True
    assert dynamo.mark_sold("p", "2026-02-02T00:00:00Z") is False
    assert posts.get_item(Key={"post_id": "p"})["Item"]["sold_at"] == (
        "2026-01-01T00:00:00Z"
    )


@mock_aws
def test_recheck_skips_old_sold_and_unknown(monkeypatch):
    entries = [
        _entry(1, timedelta(hours=1)),
        _entry(2, timedelta(days=8)),  # outside window
        _entry(3, timedelta(days=1)),  # already sold
        _entry(4, timedelta(days=1)),  # not in table
    ]
    mod, posts, calls = _setup_recheck(monkeypatch, entries, {}, stored=entries[:3])
    posts.update_item(
        Key={"post_id": "id3"},
        UpdateExpression="SET sold = :t",
        ExpressionAttributeValues={":t": True},
    )
    mod.lambda_handler({}, None)
    assert calls == ["https://blog.test/1"]  # only the newest fetch
    assert "Item" not in posts.get_item(Key={"post_id": "id4"})
    assert "sold_at" not in _item(posts, 3)


@mock_aws
def test_recheck_cap_and_order(monkeypatch):
    entries = [_entry(n, timedelta(hours=n)) for n in range(1, 7)]
    sold = {e["link"]: SOLD_HTML for e in entries}
    mod, posts, calls = _setup_recheck(monkeypatch, entries, sold)
    mod.lambda_handler({}, None)
    assert len(calls) == 1 + mod.MAX_RECHECKS_PER_RUN
    assert calls[1:] == [f"https://blog.test/{n}" for n in (2, 3, 4)]
    # newest reused result: no second GET for its URL, and gets sold_at
    assert calls.count("https://blog.test/1") == 1
    assert _item(posts, 1)["sold_at"] == "2026-11-13T12:00:00Z"
    assert "sold_at" not in _item(posts, 5)


@mock_aws
def test_recheck_failure_isolated(monkeypatch):
    entries = [_entry(n, timedelta(hours=n)) for n in range(1, 4)]
    sold = {
        "https://blog.test/2": RuntimeError("boom"),
        "https://blog.test/3": SOLD_HTML,
    }
    mod, posts, calls = _setup_recheck(monkeypatch, entries, sold)
    saved = []
    monkeypatch.setattr(mod, "save_metadata", lambda p: saved.append(p))
    mod.lambda_handler({}, None)
    assert saved
    assert _item(posts, 3)["sold"] is True
    assert "sold_at" not in _item(posts, 2)


@mock_aws
def test_recheck_total_failure_still_saves_metadata(monkeypatch):
    entries = [_entry(1, timedelta(hours=1))]
    mod, posts, _ = _setup_recheck(monkeypatch, entries, {})
    saved = []
    monkeypatch.setattr(mod, "save_metadata", lambda p: saved.append(p))

    def boom(ids):
        raise RuntimeError("ddb down")

    monkeypatch.setattr(mod, "get_posts", boom)
    mod.lambda_handler({}, None)
    assert saved


@mock_aws
def test_new_sold_post_has_no_sold_at(monkeypatch):
    entries = [_entry(1, timedelta(hours=1))]
    mod, posts, _ = _setup_recheck(
        monkeypatch, entries, {"https://blog.test/1": SOLD_HTML}, stored=[]
    )
    mod.lambda_handler({}, None)
    item = _item(posts, 1)
    assert item["sold"] is True
    assert "sold_at" not in item


@mock_aws
def test_seed_run_has_no_sold_at_and_no_rechecks(monkeypatch):
    mod, posts = _scraper_env()
    entries = [_entry(1, timedelta(hours=1)), _entry(2, timedelta(hours=2))]
    calls = []

    class Resp:
        text = SOLD_HTML

    class Feed:
        pass

    feed = Feed()
    feed.entries = entries
    monkeypatch.setattr(mod.feedparser, "parse", lambda url: feed)
    monkeypatch.setattr(
        mod.requests, "get", lambda url, timeout=None: calls.append(url) or Resp()
    )
    monkeypatch.setattr(mod, "extract_image_from_entry", lambda e: None)
    mod.lambda_handler({}, None)
    assert len(calls) == 1 + 2  # newest once, then one per seeded entry
    assert _item(posts, 1)["sold"] is True
    assert "sold_at" not in _item(posts, 1)


def _status_env():
    ddb = boto3.client("dynamodb", region_name="us-east-1")
    ddb.create_table(
        TableName="Posts",
        KeySchema=[{"AttributeName": "post_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "post_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    os.environ["POSTS_TABLE"] = "Posts"
    table = boto3.resource("dynamodb", region_name="us-east-1").Table("Posts")
    return reload_module("status_lambda"), table


@mock_aws
def test_status_recent_releases_sorted_filtered_and_shaped():
    mod, table = _status_env()
    table.put_item(Item={"post_id": "__meta__", "last_run_time": "1"})
    table.put_item(Item={"post_id": "__stats__#2026-11", "posts_announced": 1})
    # "Fri" < "Mon" < "Tue" as strings but chronologically Tue 3rd < Fri 6th < Mon 9th
    table.put_item(
        Item={
            "post_id": "a",
            "title": "A",
            "url": "u1",
            "published": "Fri, 06 Nov 2026 10:00:00 +0000",
            "sold": True,
            "sold_at": "2026-11-06T10:07:00Z",
            "image_url": "i",
        }
    )
    table.put_item(
        Item={
            "post_id": "b",
            "title": "B",
            "url": "u2",
            "published": "Mon, 09 Nov 2026 10:00:00 +0000",
            "sold": False,
        }
    )
    table.put_item(
        Item={
            "post_id": "c",
            "title": "C",
            "url": "u3",
            "published": "Tue, 03 Nov 2026 10:00:00 +0000",
            "sold": True,
        }
    )
    body = json.loads(mod.lambda_handler({}, None)["body"])
    assert body["last_run_time"] == "1"
    rr = body["recent_releases"]
    assert [r["title"] for r in rr] == ["B", "A", "C"]
    assert set(rr[0]) == {"title", "url", "published", "image_url", "sold", "sold_at"}
    assert rr[0]["sold_at"] is None and rr[0]["image_url"] is None
    assert rr[1]["sold_at"] == "2026-11-06T10:07:00Z"


@mock_aws
def test_status_recent_releases_limit_and_pagination(monkeypatch):
    mod, table = _status_env()
    for n in range(1, 16):
        table.put_item(
            Item={
                "post_id": f"p{n}",
                "title": f"P{n}",
                "url": "u",
                "published": f"Mon, {n:02d} Dec 2026 10:00:00 +0000",
                "sold": False,
            }
        )
    real_scan = mod.table.scan
    pages = []

    def paged(**kw):
        pages.append(1)
        return real_scan(Limit=4, **kw)

    monkeypatch.setattr(mod.table, "scan", paged)
    rr = json.loads(mod.lambda_handler({}, None)["body"])["recent_releases"]
    assert len(pages) > 1
    assert len(rr) == 10
    assert rr[0]["title"] == "P15"


@mock_aws
def test_status_recent_releases_empty_and_scan_failure(monkeypatch):
    mod, table = _status_env()
    table.put_item(Item={"post_id": "__meta__", "last_run_time": "1"})
    result = mod.lambda_handler({}, None)
    assert result["statusCode"] == 200
    assert json.loads(result["body"])["recent_releases"] == []

    def boom(**kw):
        raise RuntimeError("x")

    monkeypatch.setattr(mod.table, "scan", boom)
    result = mod.lambda_handler({}, None)
    assert json.loads(result["body"])["recent_releases"] == []
