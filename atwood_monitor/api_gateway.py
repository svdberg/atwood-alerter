# api_gateway.py

from aws_cdk import aws_apigateway as apigateway
from constructs import Construct
from .environments import EnvironmentConfig


def setup_api_gateway(scope: Construct, status_lambda, subscribe_lambda, register_web_push_lambda, env_config: EnvironmentConfig):
    api = apigateway.LambdaRestApi(
        scope, "StatusApi",
        handler=status_lambda,
        proxy=False,
        rest_api_name=f"{env_config.resource_name_prefix}-api",
        description=f"Public API for blog scraper status ({env_config.name})"
    )

    # /status
    status_resource = api.root.add_resource("status")
    status_resource.add_method("GET")

    # /subscribe
    subscribe_resource = api.root.add_resource("subscribe")
    subscribe_resource.add_method(
        "POST", apigateway.LambdaIntegration(subscribe_lambda, proxy=True)
    )
    add_cors_options(subscribe_resource, methods="POST,OPTIONS")

    # /register-subscription
    web_subscribe_resource = api.root.add_resource("register-subscription")
    web_subscribe_resource.add_method(
        "POST", apigateway.LambdaIntegration(register_web_push_lambda)
    )
    add_cors_options(web_subscribe_resource, methods="POST,OPTIONS")

    return api


def add_cors_options(resource, methods="POST,OPTIONS"):
    resource.add_method(
        "OPTIONS",
        apigateway.MockIntegration(
            integration_responses=[
                apigateway.IntegrationResponse(
                    status_code="200",
                    response_parameters={
                        "method.response.header.Access-Control-Allow-Origin": "'*'",
                        "method.response.header.Access-Control-Allow-Headers": "'Content-Type,X-Amz-Date,Authorization,X-Api-Key'",
                        "method.response.header.Access-Control-Allow-Methods": f"'{methods}'",
                    },
                )
            ],
            passthrough_behavior=apigateway.PassthroughBehavior.NEVER,
            request_templates={"application/json": '{"statusCode": 200}'},
        ),
        method_responses=[
            apigateway.MethodResponse(
                status_code="200",
                response_parameters={
                    "method.response.header.Access-Control-Allow-Origin": True,
                    "method.response.header.Access-Control-Allow-Headers": True,
                    "method.response.header.Access-Control-Allow-Methods": True,
                },
            )
        ],
    )
