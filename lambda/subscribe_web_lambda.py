import hashlib
import json
import os

import boto3
from http_response import json_response

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["WEB_PUSH_TABLE"])


def lambda_handler(event, context):
    try:
        # Parse body depending on whether it's from API Gateway
        if "body" in event:
            body = json.loads(event["body"])
        else:
            body = event  # for direct testing

        # Sanity check
        if "endpoint" not in body:
            return json_response(400, {"error": "Missing endpoint in subscription"})

        # Use endpoint as part of a hash ID
        subscription_json = json.dumps(body)
        subscription_id = hashlib.sha256(subscription_json.encode()).hexdigest()

        # Don't write a "ttl" attribute: it would turn on expiry for this table.
        # Save to DynamoDB
        table.put_item(
            Item={
                "subscription_id": subscription_id,
                "subscription": subscription_json,
            }
        )

        return json_response(200, {"message": "Subscription registered"})
    except Exception as e:
        print(f"Error: {e}")
        return json_response(500, {"error": str(e)})
