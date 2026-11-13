import json
import os

import boto3
from http_response import json_response

dynamodb = boto3.resource("dynamodb")
sns = boto3.client("sns")

USERS_TABLE = os.environ["USERS_TABLE"]
NOTIFY_TOPIC_ARN = os.environ["NOTIFY_TOPIC_ARN"]
table = dynamodb.Table(USERS_TABLE)

INVALID_EMAIL_MESSAGE = "Please enter a valid email address."


def lambda_handler(event, context):
    raw = event.get("body")
    if not raw:
        return json_response(400, {"error": INVALID_EMAIL_MESSAGE})

    try:
        body = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return json_response(400, {"error": "Invalid request body."})
    if not isinstance(body, dict):
        return json_response(400, {"error": "Invalid request body."})

    email = body.get("email")
    if not isinstance(email, str) or not email or "@" not in email:
        return json_response(400, {"error": INVALID_EMAIL_MESSAGE})

    try:
        # Save user to DynamoDB
        table.put_item(Item={"user_id": email})

        # Subscribe to SNS topic
        sns.subscribe(TopicArn=NOTIFY_TOPIC_ARN, Protocol="email", Endpoint=email)
    except Exception as e:
        # Log details server-side only; never include the email address (PII).
        print(f"subscribe failed: {type(e).__name__}: {e}")
        return json_response(
            500, {"error": "Something went wrong. Please try again later."}
        )

    return json_response(
        200, {"message": "Subscription requested. Check your email to confirm."}
    )
