# lambda/status_lambda.py

import json
import os
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import boto3

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["POSTS_TABLE"])

_EPOCH_MIN = datetime.min.replace(tzinfo=timezone.utc)


def _parse_published(value) -> datetime:
    """Parse RFC 822 (feed) or ISO 8601 (seed fallback); unparseable sorts last."""
    if isinstance(value, str):
        for parser in (parsedate_to_datetime, datetime.fromisoformat):
            try:
                parsed = parser(value)
            except (TypeError, ValueError):
                continue
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
    return _EPOCH_MIN


def recent_releases(limit: int = 10) -> list:
    try:
        items: list = []
        kwargs = {
            "ProjectionExpression": (
                "post_id, title, #u, published, image_url, sold, sold_at"
            ),
            "ExpressionAttributeNames": {"#u": "url"},
        }
        while True:
            response = table.scan(**kwargs)
            items.extend(response.get("Items", []))
            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                break
            kwargs["ExclusiveStartKey"] = last_key
    except Exception as e:
        print(f"Failed to load recent releases: {e}")
        return []

    posts = [i for i in items if not str(i.get("post_id", "")).startswith("__")]
    posts.sort(key=lambda i: _parse_published(i.get("published")), reverse=True)
    return [
        {
            "title": p.get("title"),
            "url": p.get("url"),
            "published": p.get("published"),
            "image_url": p.get("image_url"),
            "sold": bool(p.get("sold", False)),
            "sold_at": p.get("sold_at"),
        }
        for p in posts[:limit]
    ]


def lambda_handler(event, context):
    response = table.get_item(Key={"post_id": "__meta__"})
    item = response.get("Item", {})

    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(
            {
                "last_run_time": item.get("last_run_time", "unknown"),
                "last_seen_post": item.get("last_seen_post", {}),
                "recent_releases": recent_releases(),
            }
        ),
    }
