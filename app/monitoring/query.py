from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.monitoring.periods import AggregationPeriod
from app.monitoring.schemas import MonitoringSessionSummary

_HISTORY_QUERY = """
WITH alarm_counts AS (
    SELECT session_id, COUNT(*) FILTER (WHERE event = 'triggered') AS event_count
    FROM alarm_events
    WHERE user_id = :user_id
      AND session_id IS NOT NULL
    GROUP BY session_id
), session_stats AS (
    SELECT
        sessions.id,
        sessions.started_at,
        sessions.ended_at,
        COUNT(records.id) AS sample_count,
        COALESCE(SUM(records.face_ratio), 0) AS face_ratio_sum,
        COALESCE(SUM(records.baby_ratio), 0) AS baby_ratio_sum,
        COALESCE(SUM(records.activity_level), 0) AS activity_level_sum,
        COUNT(records.id) FILTER (WHERE records.activity_level < 10)
            AS stationary_sample_count,
        COUNT(records.id) FILTER (
            WHERE records.activity_level >= 10 AND records.activity_level <= 30
        ) AS minor_activity_sample_count,
        COUNT(records.id) FILTER (WHERE records.activity_level > 30)
            AS major_activity_sample_count,
        COALESCE(MAX(alarm_counts.event_count), 0) AS alarm_event_count
    FROM monitoring_sessions AS sessions
    LEFT JOIN monitoring_records AS records ON records.session_id = sessions.id
    LEFT JOIN alarm_counts ON alarm_counts.session_id = sessions.id
    WHERE sessions.user_id = :user_id
      AND sessions.ended_at IS NOT NULL
    GROUP BY sessions.id
), units AS (
    SELECT
        CASE
            WHEN :period = 'session' THEN id::text
            WHEN :period = 'daily' THEN
                to_char(timezone(:timezone_name, to_timestamp(started_at)), 'YYYY-MM-DD')
            WHEN :period = 'weekly' THEN
                to_char(timezone(:timezone_name, to_timestamp(started_at)), 'IYYY-"W"IW')
            ELSE
                to_char(timezone(:timezone_name, to_timestamp(started_at)), 'YYYY-MM')
        END AS unit_key,
        CASE
            WHEN :period = 'session' THEN MIN(id::text)::uuid
            ELSE NULL
        END AS session_id,
        MIN(started_at) AS started_at,
        MAX(ended_at) AS ended_at,
        SUM(ended_at - started_at) AS duration_seconds,
        COUNT(*) AS session_count,
        SUM(sample_count) AS sample_count,
        SUM(face_ratio_sum)::double precision / NULLIF(SUM(sample_count), 0)
            AS average_face_ratio,
        SUM(baby_ratio_sum)::double precision / NULLIF(SUM(sample_count), 0)
            AS average_baby_ratio,
        SUM(activity_level_sum)::double precision / NULLIF(SUM(sample_count), 0)
            AS average_activity_level,
        SUM(stationary_sample_count) AS stationary_sample_count,
        SUM(minor_activity_sample_count) AS minor_activity_sample_count,
        SUM(major_activity_sample_count) AS major_activity_sample_count,
        SUM(alarm_event_count) AS alarm_event_count
    FROM session_stats
    GROUP BY unit_key
), counted AS (
    SELECT units.*, COUNT(*) OVER () AS total_count
    FROM units
)
SELECT *
FROM counted
ORDER BY ended_at DESC, unit_key DESC
LIMIT :limit OFFSET :offset
"""


async def query_monitoring_history(
    db: AsyncSession,
    user_id: UUID,
    period: AggregationPeriod,
    page: int,
    page_size: int,
) -> tuple[list[MonitoringSessionSummary], int]:
    """Return paginated aggregates whose atomic input is a completed session."""
    rows = (
        (
            await db.execute(
                text(_HISTORY_QUERY),
                {
                    "user_id": user_id,
                    "period": period.value,
                    "timezone_name": "Asia/Taipei",
                    "limit": page_size,
                    "offset": (page - 1) * page_size,
                },
            )
        )
        .mappings()
        .all()
    )
    total = int(rows[0]["total_count"]) if rows else 0
    items = [_history_item(row, period) for row in rows]
    return items, total


def _history_item(
    row: Any,
    period: AggregationPeriod,
) -> MonitoringSessionSummary:
    return MonitoringSessionSummary(
        key=str(row["unit_key"]),
        period=period,
        session_id=row["session_id"],
        started_at=int(row["started_at"]),
        ended_at=int(row["ended_at"]),
        duration_seconds=int(row["duration_seconds"] or 0),
        session_count=int(row["session_count"] or 0),
        sample_count=int(row["sample_count"] or 0),
        average_face_ratio=_optional_float(row["average_face_ratio"]),
        average_baby_ratio=_optional_float(row["average_baby_ratio"]),
        average_activity_level=_optional_float(row["average_activity_level"]),
        stationary_sample_count=int(row["stationary_sample_count"] or 0),
        minor_activity_sample_count=int(row["minor_activity_sample_count"] or 0),
        major_activity_sample_count=int(row["major_activity_sample_count"] or 0),
        alarm_event_count=int(row["alarm_event_count"] or 0),
    )


def _optional_float(value: object) -> float | None:
    return None if value is None else round(float(value), 2)


__all__ = ["query_monitoring_history"]
