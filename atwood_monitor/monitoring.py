# monitoring.py

from aws_cdk import (
    Duration,
    aws_cloudwatch as cw
)
from constructs import Construct
from .environments import EnvironmentConfig


def setup_dashboard(scope: Construct, env_config: EnvironmentConfig):
    dashboard = cw.Dashboard(
        scope, 
        "WebPushDashboard", 
        dashboard_name=f"{env_config.resource_name_prefix}-dashboard"
    )

    push_success_metric = cw.Metric(
        namespace="WebPushNotifications",
        metric_name="PushSuccess",
        dimensions_map={"Environment": env_config.name.title()},
        statistic="Sum",
        period=Duration.minutes(5)
    )

    push_failure_metric = cw.Metric(
        namespace="WebPushNotifications",
        metric_name="PushFailure",
        dimensions_map={"Environment": env_config.name.title()},
        statistic="Sum",
        period=Duration.minutes(5)
    )

    lambda_errors_metric = cw.Metric(
        namespace="AWS/Lambda",
        metric_name="Errors",
        dimensions_map={"FunctionName": f"{env_config.resource_name_prefix}-blog-monitor"},
        statistic="Sum",
        period=Duration.minutes(5)
    )

    lambda_duration_metric = cw.Metric(
        namespace="AWS/Lambda",
        metric_name="Duration",
        dimensions_map={"FunctionName": f"{env_config.resource_name_prefix}-blog-monitor"},
        statistic="Average",
        period=Duration.minutes(5)
    )

    dashboard.add_widgets(
        cw.GraphWidget(
            title="Push Notifications",
            left=[push_success_metric],
            right=[push_failure_metric],
            width=12,
            height=6
        ),
        cw.GraphWidget(
            title="Lambda Performance",
            left=[lambda_duration_metric],
            right=[lambda_errors_metric],
            width=12,
            height=6
        )
    )
