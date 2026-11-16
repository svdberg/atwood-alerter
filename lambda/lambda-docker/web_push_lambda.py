import json
import os
from typing import Any, Optional, Tuple
from urllib.parse import urlparse

import boto3
import requests
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


_vapid_private_key: Optional[str] = None


def get_vapid_private_key() -> str:
    """Get the VAPID private key, fetching it on first use and caching it."""
    global _vapid_private_key
    if _vapid_private_key is not None:
        return _vapid_private_key

    # First try environment variable (for CI/CD)
    key: str
    env_key = os.environ.get("VAPID_PRIVATE_KEY")
    if env_key is not None:
        key = env_key
    elif ENVIRONMENT == "staging":
        key = get_secure_param("/atwood/staging/vapid_private_key")
    else:
        key = get_secure_param("/atwood/vapid_private_key")

    _vapid_private_key = key
    return key


VAPID_SUB = "mailto:svdberg@me.com"


PUSH_TTL_SECONDS = 600
PUSH_TIMEOUT_SECONDS = 10
MAX_BODY_CHARS = 4096


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


# Reasons (normalised) that mean the push service has dropped the subscription.
SUBSCRIPTION_DEAD_REASONS = {
    "vapidpkhashmismatch",
    "baddevicetoken",
    "unregistered",
    "expiredsubscription",
    "invalidregistration",
}


def _normalise_reason(reason: str) -> str:
    return reason.lower().replace("_", "").replace("-", "").replace(" ", "")


def _first_str(value: Any) -> Optional[str]:
    return value if isinstance(value, str) and value else None


def extract_reason(body: Optional[str]) -> Optional[str]:
    """Pull a failure reason out of a push service response body."""
    if not body or not isinstance(body, str):
        return None
    try:
        data = json.loads(body[:MAX_BODY_CHARS])
    except (ValueError, RecursionError):
        return None
    if not isinstance(data, dict):
        return None

    reason = _first_str(data.get("reason"))
    if reason:
        return reason

    error = data.get("error")
    if isinstance(error, dict):
        details = error.get("details")
        if isinstance(details, list):
            for detail in details:
                if isinstance(detail, dict):
                    code = _first_str(detail.get("errorCode"))
                    if code:
                        return code
        status = _first_str(error.get("status"))
        if status:
            return status
    else:
        reason = _first_str(error)
        if reason:
            return reason

    return _first_str(data.get("message"))


def classify_failure(
    status_code: Optional[int], body: Optional[str]
) -> Tuple[str, Optional[str]]:
    """Return (action, reason); action is delete, delete_if_confirmed or keep."""
    reason = extract_reason(body)
    if status_code in (404, 410):
        return "delete", reason
    if (
        status_code in (400, 403)
        and reason is not None
        and _normalise_reason(reason) in SUBSCRIPTION_DEAD_REASONS
    ):
        return "delete_if_confirmed", reason
    return "keep", reason


def put_metric(name: str) -> None:
    cloudwatch.put_metric_data(
        Namespace="WebPushNotifications",
        MetricData=[
            {
                "MetricName": name,
                "Dimensions": [{"Name": "Environment", "Value": ENVIRONMENT.title()}],
                "Unit": "Count",
                "Value": 1,
            }
        ],
    )


def delete_subscription(subscription_id: str) -> None:
    print(f"Deleting dead subscription: {subscription_id}")
    table.delete_item(Key={"subscription_id": subscription_id})
    put_metric("PushSubscriptionDeleted")


def lambda_handler(event, context):
    vapid_private_key = get_vapid_private_key()
    # You can extract a message from the SNS payload
    for record in event["Records"]:
        msg = json.loads(record["Sns"]["Message"])
        push_data = build_push_data(msg)
        succeeded_hosts: set = set()
        candidates: list = []  # (subscription_id, host)

        # Scan all subscriptions
        response = table.scan()
        for item in response.get("Items", []):
            host = ""
            try:
                sub = json.loads(item["subscription"])

                # Extract origin for aud claim
                endpoint = sub.get("endpoint", "")
                host = urlparse(endpoint).netloc
                origin = urlparse(endpoint).scheme + "://" + urlparse(endpoint).netloc

                vapid_claims = {"sub": VAPID_SUB, "aud": origin}

                webpush(
                    subscription_info=sub,
                    data=push_data,
                    vapid_private_key=vapid_private_key,
                    vapid_claims=vapid_claims,
                    headers=push_headers(),
                    ttl=PUSH_TTL_SECONDS,
                    timeout=PUSH_TIMEOUT_SECONDS,
                )

                # Successful push
                succeeded_hosts.add(host)
                put_metric("PushSuccess")
            except WebPushException as ex:
                resp = getattr(ex, "response", None)
                status_code = getattr(resp, "status_code", None)
                text = getattr(resp, "text", None)
                body = text if isinstance(text, str) else None
                action, reason = classify_failure(status_code, body)
                print(
                    f"Push failed for {item['subscription_id']}: "
                    f"status={status_code} reason={(reason or 'none')[:100]!r} "
                    f"action={action} body={(body or '')[:200]!r}"
                )

                put_metric("PushFailure")

                if action == "delete":
                    delete_subscription(item["subscription_id"])
                elif action == "delete_if_confirmed":
                    candidates.append((item["subscription_id"], host))
            except requests.exceptions.RequestException as ex:
                # str(ex) can contain the endpoint URL/token, so don't log it.
                print(
                    f"Push request error for {item['subscription_id']}: "
                    f"{type(ex).__name__} host={host}"
                )
                put_metric("PushFailure")
            except Exception as ex:
                print(
                    f"Unexpected push error for {item.get('subscription_id')}: "
                    f"{type(ex).__name__}"
                )
                put_metric("PushFailure")

        skipped: dict = {}
        for subscription_id, host in candidates:
            if host in succeeded_hosts:
                delete_subscription(subscription_id)
            else:
                skipped[host] = skipped.get(host, 0) + 1
        for host, count in skipped.items():
            print(
                f"Skipping deletion of {count} subscriptions on {host}: "
                "no successful push to that host to confirm config"
            )
