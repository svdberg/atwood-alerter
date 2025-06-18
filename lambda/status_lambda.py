# lambda/status_lambda.py

import json
import os

import boto3

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["POSTS_TABLE"])


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
            }
        ),
    }
