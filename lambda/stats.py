"""Helpers shared by the scraper and the admin stats Lambda."""

from typing import Any


def count_email_subscriptions(sns_client: Any, topic_arn: str) -> tuple[int, int]:
    """Return (confirmed, pending) email subscription counts for a topic."""
    confirmed = 0
    pending = 0
    kwargs: dict[str, Any] = {"TopicArn": topic_arn}
    while True:
        page = sns_client.list_subscriptions_by_topic(**kwargs)
        for sub in page.get("Subscriptions", []):
            if sub.get("Protocol") != "email":
                continue
            if sub.get("SubscriptionArn") == "PendingConfirmation":
                pending += 1
            else:
                confirmed += 1
        token = page.get("NextToken")
        if not token:
            return confirmed, pending
        kwargs["NextToken"] = token
