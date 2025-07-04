import os
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class EnvironmentConfig:
    """Configuration for different deployment environments."""

    name: str
    account: str
    region: str
    domain_name: str
    certificate_arn: Optional[str] = None
    monitoring_enabled: bool = True
    debug_mode: bool = False
    scraper_schedule: str = "rate(1 minute)"  # Default scraping frequency
    admin_secret_param: str = "/atwood/admin_secret"

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary for CDK context."""
        return {
            "name": self.name,
            "account": self.account,
            "region": self.region,
            "domain_name": self.domain_name,
            "certificate_arn": self.certificate_arn,
            "monitoring_enabled": self.monitoring_enabled,
            "debug_mode": self.debug_mode,
            "scraper_schedule": self.scraper_schedule,
            "admin_secret_param": self.admin_secret_param,
        }

    @property
    def stack_name_prefix(self) -> str:
        """Generate stack name prefix based on environment."""
        return f"AtwoodMonitor-{self.name.title()}"

    @property
    def resource_name_prefix(self) -> str:
        """Generate resource name prefix based on environment."""
        return f"atwood-{self.name}"


def get_environment_config(env_name: Optional[str] = None) -> EnvironmentConfig:
    """
    Get environment configuration based on environment name or CDK context.

    Args:
        env_name: Environment name override. If not provided, uses ENVIRONMENT env var.

    Returns:
        EnvironmentConfig: Configuration for the specified environment.
    """
    if env_name is None:
        env_name = os.environ.get(
            "ENVIRONMENT", "staging"
        )  # Default to staging for safety

    # Account ID
    account_id = "242650470527"

    if env_name == "staging":
        return EnvironmentConfig(
            name="staging",
            account=account_id,
            region="us-west-2",  # Different region for staging
            domain_name="staging.atwood-sniper.com",
            certificate_arn=None,  # Will be set after certificate creation
            monitoring_enabled=True,
            debug_mode=True,
            scraper_schedule="rate(2 minutes)",  # Less frequent for staging
            admin_secret_param="/atwood/staging/admin_secret",
        )
    elif env_name == "production":
        return EnvironmentConfig(
            name="production",
            account=account_id,
            region="eu-north-1",  # Production in original region
            domain_name="atwood-sniper.com",
            certificate_arn=None,  # Will be set after certificate creation
            monitoring_enabled=True,
            debug_mode=False,
            scraper_schedule="rate(1 minute)",
            admin_secret_param="/atwood/production/admin_secret",
        )
    else:
        # If an invalid environment is specified, raise an error
        raise ValueError(
            f"Invalid environment '{env_name}'. Valid environments are: staging, production"
        )


# Environment-specific settings
ENVIRONMENTS = {
    "staging": get_environment_config("staging"),
    "production": get_environment_config("production"),
}


def get_current_environment() -> EnvironmentConfig:
    """Get the current environment configuration."""
    return get_environment_config()
