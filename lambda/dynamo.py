import boto3
import os
from datetime import datetime

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
    return 'Items' not in response or len(response['Items']) == 0

def post_table_name():
    return posts_table
