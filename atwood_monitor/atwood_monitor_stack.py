from aws_cdk import (
    Stack, Duration,
    aws_events as events,
    aws_events_targets as targets,
    CfnOutput,
)
from constructs import Construct

from .lambdas import (
    create_lambda_layer,
    create_lambda_role,
    create_scraper_lambda,
    create_status_lambda,
    create_subscribe_lambda,
    create_web_push_lambda,
    create_register_web_push_lambda
)
from .storage import create_tables
from .frontend import setup_frontend
from .api_gateway import setup_api_gateway
from .monitoring import setup_dashboard
from .environments import EnvironmentConfig


class AtwoodMonitorStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, certificate_arn: str,
                 env_config: EnvironmentConfig, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        self.env_config = env_config

        # DynamoDB and SNS setup
        posts_table, users_table, web_push_table, notify_topic, web_notify_topic = create_tables(
            self, env_config
        )

        # Lambda functions
        lambda_layer = create_lambda_layer(self, env_config)
        lambda_role = create_lambda_role(self, env_config)
        scraper_lambda = create_scraper_lambda(
            self, lambda_role, lambda_layer, posts_table, users_table, notify_topic, env_config
        )
        status_lambda = create_status_lambda(
            self, lambda_role, lambda_layer, posts_table, env_config
        )
        subscribe_lambda = create_subscribe_lambda(
            self, lambda_role, lambda_layer, users_table, notify_topic, env_config
        )
        webpush_lambda = create_web_push_lambda(self, web_push_table, web_notify_topic, env_config)
        register_web_push_lambda = create_register_web_push_lambda(
            self, lambda_role, web_push_table, env_config
        )

        # EventBridge trigger for scraping with environment-specific schedule
        rule = events.Rule(
            self, "ScrapeSchedule",
            schedule=self._create_schedule(env_config.scraper_schedule)
        )
        rule.add_target(targets.LambdaFunction(scraper_lambda))

        # API Gateway setup
        api = setup_api_gateway(
            self,
            status_lambda=status_lambda,
            subscribe_lambda=subscribe_lambda,
            register_web_push_lambda=register_web_push_lambda,
            env_config=env_config
        )

        # Frontend setup with S3, CloudFront, Route53
        setup_frontend(self, certificate_arn, webpush_lambda, env_config)

        # Monitoring Dashboard (only for staging/production)
        if env_config.monitoring_enabled:
            setup_dashboard(self, env_config)

        # Outputs
        CfnOutput(self, "Environment", value=env_config.name)
        CfnOutput(self, "DomainName", value=env_config.domain_name)
        CfnOutput(self, "ApiEndpoint", value=api.url)
        CfnOutput(self, "StackStatus", value="Deployment completed")

    def _create_schedule(self, schedule_expression: str) -> events.Schedule:
        """Create EventBridge schedule from rate expression."""
        if schedule_expression.startswith("rate("):
            # Extract the rate value
            rate_part = schedule_expression[5:-1]  # Remove "rate(" and ")"

            if "minute" in rate_part:
                minutes = int(rate_part.split()[0])
                return events.Schedule.rate(Duration.minutes(minutes))
            elif "hour" in rate_part:
                hours = int(rate_part.split()[0])
                return events.Schedule.rate(Duration.hours(hours))
            elif "day" in rate_part:
                days = int(rate_part.split()[0])
                return events.Schedule.rate(Duration.days(days))

        # If it's a cron expression, use it directly
        return events.Schedule.expression(schedule_expression)
