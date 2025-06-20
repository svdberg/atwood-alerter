import json
import os

import boto3

dynamodb = boto3.resource("dynamodb")
users_table = dynamodb.Table(os.environ["USERS_TABLE"])
web_push_table = dynamodb.Table(os.environ["WEB_PUSH_TABLE"])


def lambda_handler(event, context):
    body = json.loads(event.get("body", "{}"))
    email = body.get("email")
    sub_id = body.get("subscription_id")

    if email:
        users_table.delete_item(Key={"user_id": email})
        return {
            "statusCode": 200,
            "headers": {"Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"deleted": email}),
        }
    if sub_id:
        web_push_table.delete_item(Key={"subscription_id": sub_id})
        return {
            "statusCode": 200,
            "headers": {"Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"deleted": sub_id}),
        }

    return {"statusCode": 400, "body": "No identifier provided"}
