from enum import StrEnum


class AggregationPeriod(StrEnum):
    """Public time grains built from complete monitoring sessions."""

    SESSION = "session"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


__all__ = ["AggregationPeriod"]
