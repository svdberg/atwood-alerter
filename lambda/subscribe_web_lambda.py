import hashlib
import json
import os
import time

import boto3

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
            return _response(
                400, {"error": "Missing endpoint in subscription"}
            )

        # Use endpoint as part of a hash ID
        subscription_json = json.dumps(body)
        subscription_id = hashlib.sha256(
            subscription_json.encode()
        ).hexdigest()

        # Set TTL to 30 days from now (in seconds since epoch)
        ttl_seconds = int(time.time()) + (30 * 24 * 60 * 60)

        # Save to DynamoDB
        table.put_item(Item={
            "subscription_id": subscription_id,
            "subscription": subscription_json,
            "ttl_seconds": ttl_seconds
        })

        return _response(200, {"message": "Subscription registered"})
    except Exception as e:
        print(f"Error: {e}")
        return _response(500, {"error": str(e)})



def _response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Access-Control-Allow-Origin": "*",  # CORS
            "Access-Control-Allow-Headers": "*",
        },
        "body": json.dumps(body)
    }
