import os

import boto3

ssm = boto3.client("ssm")
param_name = os.environ["ADMIN_SECRET_PARAM"]


def lambda_handler(event, context):
    token = event.get("authorizationToken", "")

    secret = ssm.get_parameter(Name=param_name, WithDecryption=True)["Parameter"][
        "Value"
    ]
    effect = "Allow" if token == secret else "Deny"
    return {
        "principalId": "admin",
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "execute-api:Invoke",
                    "Effect": effect,
                    "Resource": event["methodArn"],
                }
            ],
        },
    }
