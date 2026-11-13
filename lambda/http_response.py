import json


def json_response(status_code: int, body: dict) -> dict:
    """Build an API Gateway proxy response with CORS and JSON headers."""
    return {
        "statusCode": status_code,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
            "Content-Type": "application/json",
        },
        "body": json.dumps(body),
    }
