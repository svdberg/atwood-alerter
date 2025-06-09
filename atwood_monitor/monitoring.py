# monitoring.py

from aws_cdk import (
    Duration,
    aws_cloudwatch as cw
)
from constructs import Construct


def setup_dashboard(scope: Construct):
    dashboard = cw.Dashboard(scope, "WebPushDashboard", dashboard_name="WebPushDashboard")

    push_success_metric = cw.Metric(
        namespace="WebPushNotifications",
        metric_name="PushSuccess",
        dimensions_map={"Environment": "Prod"},
        statistic="Sum",
        period=Duration.minutes(5)
    )

    push_failure_metric = cw.Metric(
        namespace="WebPushNotifications",
        metric_name="PushFailure",
        dimensions_map={"Environment": "Prod"},
        statistic="Sum",
        period=Duration.minutes(5)
    )

    dashboard.add_widgets(
        cw.GraphWidget(
            title="Push Successes and Failures",
            left=[push_success_metric],
            right=[push_failure_metric]
        )
    )
