import os
import boto3
import json
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource('dynamodb')
sns = boto3.client('sns')

USERS_TABLE = os.environ['USERS_TABLE']
NOTIFY_TOPIC_ARN = os.environ['NOTIFY_TOPIC_ARN']
table = dynamodb.Table(USERS_TABLE)

def lambda_handler(event, context):
    try:
        body = json.loads(event.get("body", "{}"))
        email = body.get("email")
        if not email or "@" not in email:
            return {"statusCode": 400, "body": "Invalid email"}

        # Save user to DynamoDB
        table.put_item(Item={"user_id": email})

        # Subscribe to SNS topic
        sns.subscribe(
            TopicArn=NOTIFY_TOPIC_ARN,
            Protocol='email',
            Endpoint=email
        )

        return {"statusCode": 200, "headers": { "Access-Control-Allow-Origin": "*" }, "body": json.dumps({"message": "Subscription requested. Check your email to confirm."})}

    except Exception as e:
        return {"statusCode": 500, "body": str(e)}
