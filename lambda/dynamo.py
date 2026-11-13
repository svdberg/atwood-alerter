import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

# DynamoDB initialization
dynamodb = boto3.resource("dynamodb")

POSTS_TABLE_NAME = os.environ["POSTS_TABLE"]
USERS_TABLE_NAME = os.environ.get("USERS_TABLE")  # Optional

posts_table = dynamodb.Table(POSTS_TABLE_NAME)
users_table = dynamodb.Table(USERS_TABLE_NAME) if USERS_TABLE_NAME else None


def is_new_post(post_id: str) -> bool:
    response = posts_table.get_item(Key={"post_id": post_id})
    return "Item" not in response


def save_post(post: dict):
    posts_table.put_item(Item=post)


def save_metadata(post: dict):
    posts_table.put_item(
        Item={
            "post_id": "__meta__",
            "last_run_time": datetime.utcnow().isoformat(),
            "last_seen_post": {
                "title": post["title"],
                "url": post["url"],
                "image_url": post["image_url"],
                "published": post["published"],
                "sold": post["sold"],
            },
        }
    )


def get_metadata() -> dict:
    response = posts_table.get_item(Key={"post_id": "__meta__"})
    return response.get("Item", {})


def get_all_users() -> list:
    if not users_table:
        return []
    response = users_table.scan()
    return response.get("Items", [])


def is_table_empty(table):
    response = table.scan(Limit=1)
    return "Items" not in response or len(response["Items"]) == 0


def post_table_name():
    return posts_table


def record_notification(email_recipients: int, now: datetime | None = None) -> None:
    """Increment the monthly notification counter (UTC month of ``now``)."""
    now = now or datetime.now(timezone.utc)
    posts_table.update_item(
        Key={"post_id": f"__stats__#{now.strftime('%Y-%m')}"},
        UpdateExpression=(
            "ADD posts_announced :one, email_recipients :n SET last_sent = :now"
        ),
        ExpressionAttributeValues={
            ":one": 1,
            ":n": email_recipients,
            ":now": now.isoformat(),
        },
    )


def get_posts(post_ids: list[str]) -> dict[str, dict]:
    """Batch-read posts by id. Returns {post_id: item} for items that exist."""
    found: dict[str, dict] = {}
    unique = list(dict.fromkeys(post_ids))
    for start in range(0, len(unique), 100):
        keys = [{"post_id": pid} for pid in unique[start : start + 100]]
        request = {POSTS_TABLE_NAME: {"Keys": keys}}
        for _ in range(5):
            response = dynamodb.batch_get_item(RequestItems=request)
            for item in response.get("Responses", {}).get(POSTS_TABLE_NAME, []):
                found[item["post_id"]] = item
            request = response.get("UnprocessedKeys") or {}
            if not request:
                break
    return found


def mark_sold(post_id: str, sold_at: str) -> bool:
    """Set sold and sold_at once. Returns False if already recorded."""
    try:
        posts_table.update_item(
            Key={"post_id": post_id},
            UpdateExpression="SET sold = :true, sold_at = :ts",
            ConditionExpression="attribute_not_exists(sold_at) AND sold = :false",
            ExpressionAttributeValues={":true": True, ":false": False, ":ts": sold_at},
        )
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        raise
