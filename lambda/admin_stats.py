import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import boto3
from stats import count_email_subscriptions

dynamodb = boto3.resource("dynamodb")
sns = boto3.client("sns")
cloudwatch = boto3.client("cloudwatch")

users_table = dynamodb.Table(os.environ["USERS_TABLE"])
web_push_table = dynamodb.Table(os.environ["WEB_PUSH_TABLE"])
posts_table = dynamodb.Table(os.environ["POSTS_TABLE"])
NOTIFY_TOPIC_ARN = os.environ["NOTIFY_TOPIC_ARN"]
ENVIRONMENT = os.environ.get("ENVIRONMENT", "staging")

MONTHS = 12


def _count(table) -> int:
    """Count all items in a table, following scan pagination."""
    total = 0
    kwargs: dict[str, Any] = {"Select": "COUNT"}
    while True:
        page = table.scan(**kwargs)
        total += int(page["Count"])
        last_key = page.get("LastEvaluatedKey")
        if not last_key:
            return total
        kwargs["ExclusiveStartKey"] = last_key


def _month_keys(now: datetime) -> list[str]:
    """The 12 month keys (YYYY-MM), oldest first, ending at now's month."""
    year, month = now.year, now.month
    keys = []
    for _ in range(MONTHS):
        keys.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return keys[::-1]


def _stats_items(months: list[str]) -> dict[str, dict]:
    keys = [{"post_id": f"__stats__#{m}"} for m in months]
    table_name = posts_table.name
    found: dict[str, dict] = {}
    pending: dict[str, Any] | None = {table_name: {"Keys": keys}}
    while pending:
        resp = dynamodb.meta.client.batch_get_item(RequestItems=pending)
        for item in resp.get("Responses", {}).get(table_name, []):
            found[item["post_id"].split("#", 1)[1]] = item
        pending = resp.get("UnprocessedKeys") or None
    return found


def _push_by_month(metric: str, months: list[str], now: datetime) -> dict[str, int]:
    first = datetime.strptime(months[0], "%Y-%m").replace(tzinfo=timezone.utc)
    resp = cloudwatch.get_metric_statistics(
        Namespace="WebPushNotifications",
        MetricName=metric,
        Dimensions=[{"Name": "Environment", "Value": ENVIRONMENT.title()}],
        StartTime=first,
        EndTime=now + timedelta(days=1),
        Period=86400,
        Statistics=["Sum"],
    )
    totals = {m: 0 for m in months}
    for point in resp.get("Datapoints", []):
        key = point["Timestamp"].strftime("%Y-%m")
        if key in totals:
            totals[key] += int(point["Sum"])
    return totals


def build_stats(now: datetime) -> dict:
    months = _month_keys(now)
    items = _stats_items(months)

    try:
        confirmed, pending = count_email_subscriptions(sns, NOTIFY_TOPIC_ARN)
        email_confirmed: int | None = confirmed
        email_pending: int | None = pending
    except Exception as e:
        print(f"SNS lookup failed: {e}")
        email_confirmed = email_pending = None

    push_success: dict[str, int] | None
    push_failure: dict[str, int] | None
    try:
        push_success = _push_by_month("PushSuccess", months, now)
        push_failure = _push_by_month("PushFailure", months, now)
    except Exception as e:
        print(f"CloudWatch lookup failed: {e}")
        push_success = push_failure = None

    monthly: list[dict[str, Any]] = []
    last_sent: str | None = None
    for m in months:
        item = items.get(m, {})
        sent = item.get("last_sent")
        if isinstance(sent, str) and (last_sent is None or sent > last_sent):
            last_sent = sent
        monthly.append(
            {
                "month": m,
                "posts_announced": int(item.get("posts_announced", Decimal(0))),
                "email_recipients": int(item.get("email_recipients", Decimal(0))),
                "push_success": push_success[m] if push_success is not None else None,
                "push_failure": push_failure[m] if push_failure is not None else None,
            }
        )

    def total(field: str) -> int | None:
        if any(row[field] is None for row in monthly):
            return None
        return sum(row[field] for row in monthly)

    users = _count(users_table)
    web_push = _count(web_push_table)
    return {
        "users": users,
        "web_push": web_push,
        "subscribers": {
            "email_confirmed": email_confirmed,
            "email_pending": email_pending,
            "web_push": web_push,
        },
        "notifications": {
            "posts_announced": total("posts_announced"),
            "email_recipients": total("email_recipients"),
            "push_success": total("push_success"),
            "push_failure": total("push_failure"),
            "last_sent": last_sent,
        },
        "monthly": monthly,
    }


def lambda_handler(event, context):
    stats = build_stats(datetime.now(timezone.utc))
    return {
        "statusCode": 200,
        "headers": {"Access-Control-Allow-Origin": "*"},
        "body": json.dumps(stats),
    }
