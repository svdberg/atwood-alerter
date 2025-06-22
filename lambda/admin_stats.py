import json
import os

import boto3

dynamodb = boto3.resource("dynamodb")
users_table = dynamodb.Table(os.environ["USERS_TABLE"])
web_push_table = dynamodb.Table(os.environ["WEB_PUSH_TABLE"])


def lambda_handler(event, context):
    users_count = users_table.scan(Select="COUNT")["Count"]
    web_push_count = web_push_table.scan(Select="COUNT")["Count"]
    return {
        "statusCode": 200,
        "headers": {"Access-Control-Allow-Origin": "*"},
        "body": json.dumps({"users": users_count, "web_push": web_push_count}),
    }
