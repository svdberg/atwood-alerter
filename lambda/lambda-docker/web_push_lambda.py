import json
import os
from urllib.parse import urlparse

import boto3
from pywebpush import WebPushException, webpush

# Get environment-specific configuration
ENVIRONMENT = os.environ.get("ENVIRONMENT", "production")
WEB_PUSH_TABLE = os.environ.get("WEB_PUSH_TABLE", "WebPushSubscriptions")

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(WEB_PUSH_TABLE)
cloudwatch = boto3.client("cloudwatch")
ssm = boto3.client("ssm")


def get_secure_param(name):
    return ssm.get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]


def get_vapid_private_key():
    """Get VAPID private key from environment variable or SSM Parameter Store."""
    # First try environment variable (for CI/CD)
    if "VAPID_PRIVATE_KEY" in os.environ:
        return os.environ["VAPID_PRIVATE_KEY"]

    # Then try environment-specific SSM parameter
    if ENVIRONMENT == "staging":
        return get_secure_param("/atwood/staging/vapid_private_key")
    else:
        return get_secure_param("/atwood/vapid_private_key")


VAPID_PRIVATE_KEY = get_vapid_private_key()
VAPID_SUB = "mailto:svdberg@me.com"


PUSH_TTL_SECONDS = 600


def build_push_data(msg: dict) -> str:
    return json.dumps(
        {
            "title": msg.get("title", "Atwood Blog"),
            "body": msg.get("body", "New post!"),
            "url": msg.get("url", "https://atwoodknives.blogspot.com/"),
            "image_url": msg.get("image_url"),
        }
    )


def push_headers() -> dict:
    # pywebpush mutates the headers dict, so never share one between calls.
    return {"Urgency": "high"}


def lambda_handler(event, context):
    # You can extract a message from the SNS payload
    for record in event["Records"]:
        msg = json.loads(record["Sns"]["Message"])
        push_data = build_push_data(msg)

        # Scan all subscriptions
        response = table.scan()
        for item in response.get("Items", []):
            try:
                sub = json.loads(item["subscription"])

                # Extract origin for aud claim
                endpoint = sub.get("endpoint", "")
                origin = urlparse(endpoint).scheme + "://" + urlparse(endpoint).netloc

                vapid_claims = {"sub": VAPID_SUB, "aud": origin}

                webpush(
                    subscription_info=sub,
                    data=push_data,
                    vapid_private_key=VAPID_PRIVATE_KEY,
                    vapid_claims=vapid_claims,
                    headers=push_headers(),
                    ttl=PUSH_TTL_SECONDS,
                )

                # Successful push
                cloudwatch.put_metric_data(
                    Namespace="WebPushNotifications",
                    MetricData=[
                        {
                            "MetricName": "PushSuccess",
                            "Dimensions": [
                                {"Name": "Environment", "Value": ENVIRONMENT.title()}
                            ],
                            "Unit": "Count",
                            "Value": 1,
                        }
                    ],
                )
            except WebPushException as ex:
                status_code = getattr(ex.response, "status_code", None)
                print(f"Push failed for {item['subscription_id']}: {ex}")

                cloudwatch.put_metric_data(
                    Namespace="WebPushNotifications",
                    MetricData=[
                        {
                            "MetricName": "PushFailure",
                            "Dimensions": [
                                {"Name": "Environment", "Value": ENVIRONMENT.title()}
                            ],
                            "Unit": "Count",
                            "Value": 1,
                        }
                    ],
                )

                # Remove stale or invalid subscriptions
                if status_code in (404, 410):
                    print(f"Deleting stale subscription: {item['subscription_id']}")
                    table.delete_item(Key={"subscription_id": item["subscription_id"]})
