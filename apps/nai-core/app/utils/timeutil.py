"""
nAI Core time helpers
"""

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Timezone-aware current UTC time."""
    return datetime.now(UTC)


def utc_now_iso() -> str:
    """Current UTC time as ISO-8601 with a trailing ``Z``."""
    return utc_now().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
