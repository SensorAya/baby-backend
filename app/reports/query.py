from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from statistics import median
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

REPORT_TIMEZONE = "Asia/Taipei"
MIN_REPORT_DAYS = 1
MAX_REPORT_DAYS = 30
IMAGE_WIDTH = 1280
IMAGE_HEIGHT = 720
LOW_VISIBILITY_THRESHOLD = 20
HIGH_VISIBILITY_THRESHOLD = 80
REPORT_ANALYSIS_VERSION = "2.0"


@dataclass(frozen=True, slots=True)
class SamplingQualitySummary:
    first_sample_at: datetime | None
    last_sample_at: datetime | None
    last_sample_age_seconds: float | None
    duplicate_timestamp_count: int
    median_interval_seconds: float | None
    nominal_interval_seconds: int
    nominal_interval_source: str
    p90_interval_seconds: float | None
    longest_interval_seconds: float | None
    continuity_gap_threshold_seconds: int
    state_hold_cap_seconds: int
    discontinuity_count: int
    estimated_observed_seconds: float
    observed_window_coverage_percentage: float


@dataclass(frozen=True, slots=True)
class EventSummary:
    episode_count: int
    estimated_duration_seconds: float
    longest_episode_seconds: float


@dataclass(frozen=True, slots=True)
class FaceVisibilityTrend:
    active_day_count: int
    eligible_day_count: int
    excluded_day_count: int
    direction: str
    theil_sen_slope_points_per_day: float | None
    estimated_change_points: float | None
    first_window_median: float | None
    last_window_median: float | None
    window_difference_points: float | None
    evidence_level: str


@dataclass(frozen=True, slots=True)
class MonitoringSummary:
    sample_count: int
    estimated_observed_seconds: float
    sample_average_face_ratio: float | None
    time_weighted_average_face_ratio: float | None
    median_face_ratio: float | None
    p10_face_ratio: float | None
    p90_face_ratio: float | None
    face_ratio_standard_deviation: float | None
    minimum_face_ratio: int | None
    maximum_face_ratio: int | None
    alarm_sample_count: int
    no_face_sample_count: int
    low_visibility_sample_count: int
    high_visibility_sample_count: int
    visible_center_sample_count: int
    invalid_center_sample_count: int
    average_face_center_x: float | None
    average_face_center_y: float | None
    normalized_center_x: float | None
    normalized_center_y: float | None
    normalized_center_x_standard_deviation: float | None
    normalized_center_y_standard_deviation: float | None
    edge_center_sample_count: int
    alarm_episode_count: int
    no_face_episode_count: int
    low_visibility_episode_count: int
    estimated_alarm_seconds: float
    estimated_no_face_seconds: float
    estimated_low_visibility_seconds: float
    estimated_high_visibility_seconds: float
    discontinuity_count: int
    longest_interval_seconds: float | None


@dataclass(frozen=True, slots=True)
class DailyMonitoringSummary(MonitoringSummary):
    day: date


@dataclass(frozen=True, slots=True)
class MonitoringReportData:
    days: int
    timezone_name: str
    start_at: datetime
    end_at: datetime
    daily: tuple[DailyMonitoringSummary, ...]
    period: MonitoringSummary
    sampling_quality: SamplingQualitySummary
    alarm_events: EventSummary
    no_face_events: EventSummary
    low_visibility_events: EventSummary
    face_visibility_trend: FaceVisibilityTrend

    @property
    def total_sample_count(self) -> int:
        return self.period.sample_count

    @property
    def active_day_count(self) -> int:
        return sum(summary.sample_count > 0 for summary in self.daily)


async def query_monitoring_report_data(
    db: AsyncSession,
    user_id: UUID,
    days: int,
    *,
    now: datetime | None = None,
) -> MonitoringReportData:
    """Query robust report statistics for recent local calendar days.

    The report does not assume a configured sampling frequency. A nominal interval is
    inferred from the median positive interval. Time-weighted metrics cap how long a
    sample may represent, preventing long upload gaps from being counted as continuous
    observation.
    """
    if not MIN_REPORT_DAYS <= days <= MAX_REPORT_DAYS:
        raise ValueError(
            f"days must be between {MIN_REPORT_DAYS} and {MAX_REPORT_DAYS}"
        )

    report_timezone = ZoneInfo(REPORT_TIMEZONE)
    end_at = now or datetime.now(timezone.utc)
    if end_at.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    end_at = end_at.astimezone(timezone.utc)

    end_local = end_at.astimezone(report_timezone)
    start_day = end_local.date() - timedelta(days=days - 1)
    start_local = datetime.combine(start_day, time.min, tzinfo=report_timezone)
    start_at = start_local.astimezone(timezone.utc)

    params: dict[str, Any] = {
        "user_id": user_id,
        "start_timestamp": int(start_at.timestamp()),
        "end_timestamp": int(end_at.timestamp()),
        "timezone_name": REPORT_TIMEZONE,
        "low_visibility_threshold": LOW_VISIBILITY_THRESHOLD,
        "high_visibility_threshold": HIGH_VISIBILITY_THRESHOLD,
        "image_width": IMAGE_WIDTH,
        "image_height": IMAGE_HEIGHT,
        "edge_left": IMAGE_WIDTH * 0.1,
        "edge_right": IMAGE_WIDTH * 0.9,
        "edge_top": IMAGE_HEIGHT * 0.1,
        "edge_bottom": IMAGE_HEIGHT * 0.9,
    }

    interval_row = (await db.execute(text(_INTERVAL_QUERY), params)).mappings().one()
    median_interval = _optional_float(interval_row["median_interval_seconds"])
    nominal_interval = max(1, round(median_interval or 10.0))
    gap_threshold = max(60, nominal_interval * 5)
    state_hold_cap = min(gap_threshold, max(30, nominal_interval * 2))
    params.update(
        {
            "nominal_interval": nominal_interval,
            "gap_threshold": gap_threshold,
            "state_hold_cap": state_hold_cap,
        }
    )

    daily_rows = (await db.execute(text(_DAILY_SUMMARY_QUERY), params)).mappings().all()
    daily_by_day = {
        row["local_day"]: _summary_from_row(row, day=row["local_day"])
        for row in daily_rows
    }
    daily = tuple(
        daily_by_day.get(day, _empty_daily_summary(day))
        for day in (start_day + timedelta(days=offset) for offset in range(days))
    )

    period_row = (
        (await db.execute(text(_PERIOD_SUMMARY_QUERY), params)).mappings().one()
    )
    period = _summary_from_row(period_row)

    event_row = (await db.execute(text(_EVENT_QUERY), params)).mappings().one()
    alarm_events = EventSummary(
        episode_count=int(event_row["alarm_episode_count"] or 0),
        estimated_duration_seconds=float(event_row["alarm_duration_seconds"] or 0),
        longest_episode_seconds=float(event_row["longest_alarm_episode_seconds"] or 0),
    )
    no_face_events = EventSummary(
        episode_count=int(event_row["no_face_episode_count"] or 0),
        estimated_duration_seconds=float(event_row["no_face_duration_seconds"] or 0),
        longest_episode_seconds=float(
            event_row["longest_no_face_episode_seconds"] or 0
        ),
    )
    low_visibility_events = EventSummary(
        episode_count=int(event_row["low_visibility_episode_count"] or 0),
        estimated_duration_seconds=float(
            event_row["low_visibility_duration_seconds"] or 0
        ),
        longest_episode_seconds=float(
            event_row["longest_low_visibility_episode_seconds"] or 0
        ),
    )

    period_seconds = max((end_at - start_at).total_seconds(), 1.0)
    observed_seconds = period.estimated_observed_seconds
    first_sample_at = _timestamp_to_datetime(interval_row["first_timestamp"])
    last_sample_at = _timestamp_to_datetime(interval_row["last_timestamp"])
    sampling_quality = SamplingQualitySummary(
        first_sample_at=first_sample_at,
        last_sample_at=last_sample_at,
        last_sample_age_seconds=(
            None
            if last_sample_at is None
            else max((end_at - last_sample_at).total_seconds(), 0.0)
        ),
        duplicate_timestamp_count=int(interval_row["duplicate_timestamp_count"] or 0),
        median_interval_seconds=median_interval,
        nominal_interval_seconds=nominal_interval,
        nominal_interval_source=(
            "median_positive_interval"
            if median_interval is not None
            else "fallback_10_seconds"
        ),
        p90_interval_seconds=_optional_float(interval_row["p90_interval_seconds"]),
        longest_interval_seconds=_optional_float(
            interval_row["longest_interval_seconds"]
        ),
        continuity_gap_threshold_seconds=gap_threshold,
        state_hold_cap_seconds=state_hold_cap,
        discontinuity_count=period.discontinuity_count,
        estimated_observed_seconds=observed_seconds,
        observed_window_coverage_percentage=min(
            observed_seconds / period_seconds * 100,
            100.0,
        ),
    )

    return MonitoringReportData(
        days=days,
        timezone_name=REPORT_TIMEZONE,
        start_at=start_at,
        end_at=end_at,
        daily=daily,
        period=period,
        sampling_quality=sampling_quality,
        alarm_events=alarm_events,
        no_face_events=no_face_events,
        low_visibility_events=low_visibility_events,
        face_visibility_trend=_calculate_face_visibility_trend(daily),
    )


def format_monitoring_report_data(data: MonitoringReportData) -> str:
    """Serialize derived facts as stable JSON for the LLM.

    JSON reduces ambiguity compared with compact prose and keeps methodology,
    measured values, and limitations separated.
    """
    report_timezone = ZoneInfo(data.timezone_name)
    start_local = data.start_at.astimezone(report_timezone)
    end_local = data.end_at.astimezone(report_timezone)

    payload = {
        "analysis_version": REPORT_ANALYSIS_VERSION,
        "report_window": {
            "timezone": data.timezone_name,
            "start_local": start_local.isoformat(),
            "end_local": end_local.isoformat(),
            "calendar_days": data.days,
            "active_days": data.active_day_count,
            "missing_days": [
                summary.day.isoformat()
                for summary in data.daily
                if summary.sample_count == 0
            ],
        },
        "methodology": {
            "face_ratio_semantics": (
                "Percentage of frames containing a detected face in the prior "
                "10-second sliding window; it is not a direct measurement of "
                "the baby's presence or safety."
            ),
            "sample_metrics": (
                "Counts and percentiles describe uploaded samples. They do not "
                "equal elapsed time when sampling is irregular."
            ),
            "time_weighting": (
                "Each sample represents time until the next sample, capped at "
                f"{data.sampling_quality.state_hold_cap_seconds} seconds. This "
                "prevents long upload gaps from being treated as continuous "
                "observation."
            ),
            "episode_segmentation": (
                "A new alarm/no-face/low-visibility episode starts on a state "
                "transition or "
                "after a sampling discontinuity longer than "
                f"{data.sampling_quality.continuity_gap_threshold_seconds} seconds."
            ),
            "visibility_thresholds": {
                "no_face": "face_ratio == 0",
                "low_visibility": (f"face_ratio < {LOW_VISIBILITY_THRESHOLD}"),
                "high_visibility": (f"face_ratio >= {HIGH_VISIBILITY_THRESHOLD}"),
            },
            "framing": (
                f"Face centers are normalized from a {IMAGE_WIDTH}x{IMAGE_HEIGHT} "
                "image. Edge-center means the center lies in the outer 10% border."
            ),
            "trend": (
                "Daily time-weighted averages are summarized with a Theil-Sen "
                "median slope. Days with fewer than 3 samples or less than 10% "
                "of the typical active-day observed time are excluded from trend "
                "estimation."
            ),
        },
        "data_quality": _sampling_quality_dict(data.sampling_quality),
        "period_summary": _summary_dict(data.period),
        "alarm_events": _event_dict(data.alarm_events),
        "no_face_events": _event_dict(data.no_face_events),
        "low_visibility_events": _event_dict(data.low_visibility_events),
        "face_visibility_trend": _trend_dict(data.face_visibility_trend),
        "daily_summaries": [
            _daily_summary_dict(summary, data) for summary in data.daily
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False)


async def query_monitoring_report_text(
    db: AsyncSession,
    user_id: UUID,
    days: int,
    *,
    now: datetime | None = None,
) -> str:
    """Query and format monitoring data for internal report generation."""
    data = await query_monitoring_report_data(db, user_id, days, now=now)
    return format_monitoring_report_data(data)


def _calculate_face_visibility_trend(
    daily: tuple[DailyMonitoringSummary, ...],
) -> FaceVisibilityTrend:
    candidates = [
        summary
        for summary in daily
        if summary.time_weighted_average_face_ratio is not None
    ]
    active_day_count = len(candidates)
    typical_observed_seconds = (
        float(median(summary.estimated_observed_seconds for summary in candidates))
        if candidates
        else 0.0
    )
    minimum_observed_seconds = typical_observed_seconds * 0.1
    eligible = [
        summary
        for summary in candidates
        if summary.sample_count >= 3
        and summary.estimated_observed_seconds >= minimum_observed_seconds
    ]
    points = [
        (summary.day.toordinal(), summary.time_weighted_average_face_ratio)
        for summary in eligible
    ]
    eligible_day_count = len(points)
    excluded_day_count = active_day_count - eligible_day_count

    if eligible_day_count < 3:
        return FaceVisibilityTrend(
            active_day_count=active_day_count,
            eligible_day_count=eligible_day_count,
            excluded_day_count=excluded_day_count,
            direction="insufficient_data",
            theil_sen_slope_points_per_day=None,
            estimated_change_points=None,
            first_window_median=None,
            last_window_median=None,
            window_difference_points=None,
            evidence_level="insufficient",
        )

    slopes = [
        (later_value - earlier_value) / (later_day - earlier_day)
        for index, (earlier_day, earlier_value) in enumerate(points)
        for later_day, later_value in points[index + 1 :]
        if later_day > earlier_day
    ]
    slope = float(median(slopes))
    span_days = points[-1][0] - points[0][0]
    estimated_change = slope * span_days

    window_size = max(1, eligible_day_count // 3)
    first_window = float(median(value for _, value in points[:window_size]))
    last_window = float(median(value for _, value in points[-window_size:]))
    window_difference = last_window - first_window

    if abs(estimated_change) < 5 and abs(window_difference) < 5:
        direction = "stable_or_small_change"
    elif estimated_change > 0 and window_difference > 0:
        direction = "increasing"
    elif estimated_change < 0 and window_difference < 0:
        direction = "decreasing"
    else:
        direction = "mixed"

    evidence_level = "moderate" if eligible_day_count >= 5 else "limited"
    return FaceVisibilityTrend(
        active_day_count=active_day_count,
        eligible_day_count=eligible_day_count,
        excluded_day_count=excluded_day_count,
        direction=direction,
        theil_sen_slope_points_per_day=slope,
        estimated_change_points=estimated_change,
        first_window_median=first_window,
        last_window_median=last_window,
        window_difference_points=window_difference,
        evidence_level=evidence_level,
    )


def _summary_from_row(
    row: Any,
    *,
    day: date | None = None,
) -> MonitoringSummary | DailyMonitoringSummary:
    values = {
        "sample_count": int(row["sample_count"] or 0),
        "estimated_observed_seconds": float(row["estimated_observed_seconds"] or 0),
        "sample_average_face_ratio": _optional_float(row["sample_average_face_ratio"]),
        "time_weighted_average_face_ratio": _optional_float(
            row["time_weighted_average_face_ratio"]
        ),
        "median_face_ratio": _optional_float(row["median_face_ratio"]),
        "p10_face_ratio": _optional_float(row["p10_face_ratio"]),
        "p90_face_ratio": _optional_float(row["p90_face_ratio"]),
        "face_ratio_standard_deviation": _optional_float(
            row["face_ratio_standard_deviation"]
        ),
        "minimum_face_ratio": _optional_int(row["minimum_face_ratio"]),
        "maximum_face_ratio": _optional_int(row["maximum_face_ratio"]),
        "alarm_sample_count": int(row["alarm_sample_count"] or 0),
        "no_face_sample_count": int(row["no_face_sample_count"] or 0),
        "low_visibility_sample_count": int(row["low_visibility_sample_count"] or 0),
        "high_visibility_sample_count": int(row["high_visibility_sample_count"] or 0),
        "visible_center_sample_count": int(row["visible_center_sample_count"] or 0),
        "invalid_center_sample_count": int(row["invalid_center_sample_count"] or 0),
        "average_face_center_x": _optional_float(row["average_face_center_x"]),
        "average_face_center_y": _optional_float(row["average_face_center_y"]),
        "normalized_center_x": _optional_float(row["normalized_center_x"]),
        "normalized_center_y": _optional_float(row["normalized_center_y"]),
        "normalized_center_x_standard_deviation": _optional_float(
            row["normalized_center_x_standard_deviation"]
        ),
        "normalized_center_y_standard_deviation": _optional_float(
            row["normalized_center_y_standard_deviation"]
        ),
        "edge_center_sample_count": int(row["edge_center_sample_count"] or 0),
        "alarm_episode_count": int(row["alarm_episode_count"] or 0),
        "no_face_episode_count": int(row["no_face_episode_count"] or 0),
        "low_visibility_episode_count": int(row["low_visibility_episode_count"] or 0),
        "estimated_alarm_seconds": float(row["estimated_alarm_seconds"] or 0),
        "estimated_no_face_seconds": float(row["estimated_no_face_seconds"] or 0),
        "estimated_low_visibility_seconds": float(
            row["estimated_low_visibility_seconds"] or 0
        ),
        "estimated_high_visibility_seconds": float(
            row["estimated_high_visibility_seconds"] or 0
        ),
        "discontinuity_count": int(row["discontinuity_count"] or 0),
        "longest_interval_seconds": _optional_float(row["longest_interval_seconds"]),
    }
    if day is not None:
        return DailyMonitoringSummary(day=day, **values)
    return MonitoringSummary(**values)


def _empty_daily_summary(day: date) -> DailyMonitoringSummary:
    return DailyMonitoringSummary(
        day=day,
        sample_count=0,
        estimated_observed_seconds=0,
        sample_average_face_ratio=None,
        time_weighted_average_face_ratio=None,
        median_face_ratio=None,
        p10_face_ratio=None,
        p90_face_ratio=None,
        face_ratio_standard_deviation=None,
        minimum_face_ratio=None,
        maximum_face_ratio=None,
        alarm_sample_count=0,
        no_face_sample_count=0,
        low_visibility_sample_count=0,
        high_visibility_sample_count=0,
        visible_center_sample_count=0,
        invalid_center_sample_count=0,
        average_face_center_x=None,
        average_face_center_y=None,
        normalized_center_x=None,
        normalized_center_y=None,
        normalized_center_x_standard_deviation=None,
        normalized_center_y_standard_deviation=None,
        edge_center_sample_count=0,
        alarm_episode_count=0,
        no_face_episode_count=0,
        low_visibility_episode_count=0,
        estimated_alarm_seconds=0,
        estimated_no_face_seconds=0,
        estimated_low_visibility_seconds=0,
        estimated_high_visibility_seconds=0,
        discontinuity_count=0,
        longest_interval_seconds=None,
    )


def _summary_dict(summary: MonitoringSummary) -> dict[str, Any]:
    result = asdict(summary)
    result.pop("day", None)
    sample_count = summary.sample_count
    observed_seconds = summary.estimated_observed_seconds
    visible_count = summary.visible_center_sample_count
    result.update(
        {
            "alarm_sample_percentage": _percentage(
                summary.alarm_sample_count,
                sample_count,
            ),
            "no_face_sample_percentage": _percentage(
                summary.no_face_sample_count,
                sample_count,
            ),
            "low_visibility_sample_percentage": _percentage(
                summary.low_visibility_sample_count,
                sample_count,
            ),
            "high_visibility_sample_percentage": _percentage(
                summary.high_visibility_sample_count,
                sample_count,
            ),
            "visible_center_sample_percentage": _percentage(
                summary.visible_center_sample_count,
                sample_count,
            ),
            "invalid_center_sample_percentage": _percentage(
                summary.invalid_center_sample_count,
                sample_count,
            ),
            "edge_center_percentage_of_visible": _percentage(
                summary.edge_center_sample_count,
                visible_count,
            ),
            "estimated_alarm_time_percentage": _percentage(
                summary.estimated_alarm_seconds,
                observed_seconds,
            ),
            "estimated_no_face_time_percentage": _percentage(
                summary.estimated_no_face_seconds,
                observed_seconds,
            ),
            "estimated_low_visibility_time_percentage": _percentage(
                summary.estimated_low_visibility_seconds,
                observed_seconds,
            ),
            "estimated_high_visibility_time_percentage": _percentage(
                summary.estimated_high_visibility_seconds,
                observed_seconds,
            ),
        }
    )
    return _round_nested(result)


def _daily_summary_dict(
    summary: DailyMonitoringSummary,
    data: MonitoringReportData,
) -> dict[str, Any]:
    report_timezone = ZoneInfo(data.timezone_name)
    report_start = data.start_at.astimezone(report_timezone)
    report_end = data.end_at.astimezone(report_timezone)
    day_start = datetime.combine(summary.day, time.min, tzinfo=report_timezone)
    day_end = day_start + timedelta(days=1)
    clipped_start = max(day_start, report_start)
    clipped_end = min(day_end, report_end)
    day_window_seconds = max((clipped_end - clipped_start).total_seconds(), 0.0)
    day_coverage = _round_nested(
        _percentage(summary.estimated_observed_seconds, day_window_seconds)
    )

    if summary.sample_count == 0:
        return {
            "day": summary.day.isoformat(),
            "status": "no_data",
            "sample_count": 0,
            "day_window_seconds": round(day_window_seconds, 2),
            "estimated_day_coverage_percentage": day_coverage,
        }

    full = _summary_dict(summary)
    selected_keys = (
        "sample_count",
        "estimated_observed_seconds",
        "sample_average_face_ratio",
        "time_weighted_average_face_ratio",
        "median_face_ratio",
        "p10_face_ratio",
        "p90_face_ratio",
        "no_face_sample_percentage",
        "low_visibility_sample_percentage",
        "high_visibility_sample_percentage",
        "estimated_no_face_time_percentage",
        "estimated_low_visibility_time_percentage",
        "estimated_high_visibility_time_percentage",
        "no_face_episode_count",
        "low_visibility_episode_count",
        "alarm_sample_percentage",
        "estimated_alarm_time_percentage",
        "alarm_episode_count",
        "visible_center_sample_percentage",
        "invalid_center_sample_count",
        "invalid_center_sample_percentage",
        "normalized_center_x",
        "normalized_center_y",
        "normalized_center_x_standard_deviation",
        "normalized_center_y_standard_deviation",
        "edge_center_percentage_of_visible",
        "discontinuity_count",
        "longest_interval_seconds",
    )
    result = {
        "day": summary.day.isoformat(),
        "status": "observed",
        "day_window_seconds": round(day_window_seconds, 2),
        "estimated_day_coverage_percentage": day_coverage,
    }
    result.update(
        {key: full[key] for key in selected_keys if full.get(key) is not None}
    )
    return result


def _sampling_quality_dict(summary: SamplingQualitySummary) -> dict[str, Any]:
    result = asdict(summary)
    result["first_sample_at"] = _isoformat(summary.first_sample_at)
    result["last_sample_at"] = _isoformat(summary.last_sample_at)
    result["coverage_interpretation"] = (
        "Estimated share of the full report window supported by nearby samples. "
        "It is not device uptime or proof that an expected schedule was met."
    )
    return _round_nested(result)


def _event_dict(summary: EventSummary) -> dict[str, Any]:
    return _round_nested(asdict(summary))


def _trend_dict(summary: FaceVisibilityTrend) -> dict[str, Any]:
    return _round_nested(asdict(summary))


def _percentage(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator * 100


def _round_nested(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 2)
    if isinstance(value, dict):
        return {key: _round_nested(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_round_nested(item) for item in value]
    return value


def _timestamp_to_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(int(value), tz=timezone.utc)


def _isoformat(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _optional_float(value: object) -> float | None:
    return None if value is None else float(value)


def _optional_int(value: object) -> int | None:
    return None if value is None else int(value)


_INTERVAL_QUERY = """
WITH ordered AS (
    SELECT
        timestamp,
        timestamp - LAG(timestamp) OVER (ORDER BY timestamp, id) AS interval_seconds
    FROM monitoring_records
    WHERE user_id = :user_id
      AND timestamp >= :start_timestamp
      AND timestamp <= :end_timestamp
)
SELECT
    MIN(timestamp) AS first_timestamp,
    MAX(timestamp) AS last_timestamp,
    COUNT(*) FILTER (WHERE interval_seconds = 0) AS duplicate_timestamp_count,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY interval_seconds)
        FILTER (WHERE interval_seconds > 0) AS median_interval_seconds,
    percentile_cont(0.9) WITHIN GROUP (ORDER BY interval_seconds)
        FILTER (WHERE interval_seconds > 0) AS p90_interval_seconds,
    MAX(interval_seconds) FILTER (WHERE interval_seconds > 0)
        AS longest_interval_seconds
FROM ordered
"""

_COMMON_CTE = """
WITH ordered AS (
    SELECT
        id,
        timestamp,
        face_ratio,
        face_center_x,
        face_center_y,
        alarm_active,
        LAG(timestamp) OVER (ORDER BY timestamp, id) AS previous_timestamp,
        LEAD(timestamp) OVER (ORDER BY timestamp, id) AS next_timestamp,
        LAG(alarm_active) OVER (ORDER BY timestamp, id) AS previous_alarm_active,
        LAG(face_ratio) OVER (ORDER BY timestamp, id) AS previous_face_ratio
    FROM monitoring_records
    WHERE user_id = :user_id
      AND timestamp >= :start_timestamp
      AND timestamp <= :end_timestamp
), prepared AS (
    SELECT
        *,
        timezone(:timezone_name, to_timestamp(timestamp))::date AS local_day,
        LEAST(
            GREATEST(
                COALESCE(
                    next_timestamp - timestamp,
                    LEAST(
                        GREATEST(:end_timestamp - timestamp, 0),
                        :nominal_interval
                    )
                ),
                0
            ),
            :state_hold_cap
        )::double precision AS weight_seconds,
        (
            (face_center_x <> 0 OR face_center_y <> 0)
            AND face_center_x <= :image_width
            AND face_center_y <= :image_height
        ) AS has_visible_center,
        (
            (face_center_x <> 0 OR face_center_y <> 0)
            AND (
                face_center_x > :image_width
                OR face_center_y > :image_height
            )
        ) AS has_invalid_center,
        CASE
            WHEN alarm_active IS TRUE
             AND (
                previous_alarm_active IS NOT TRUE
                OR previous_timestamp IS NULL
                OR timestamp - previous_timestamp > :gap_threshold
             )
            THEN 1 ELSE 0
        END AS alarm_episode_start,
        CASE
            WHEN face_ratio = 0
             AND (
                previous_face_ratio IS NULL
                OR previous_face_ratio <> 0
                OR previous_timestamp IS NULL
                OR timestamp - previous_timestamp > :gap_threshold
             )
            THEN 1 ELSE 0
        END AS no_face_episode_start,
        CASE
            WHEN face_ratio < :low_visibility_threshold
             AND (
                previous_face_ratio IS NULL
                OR previous_face_ratio >= :low_visibility_threshold
                OR previous_timestamp IS NULL
                OR timestamp - previous_timestamp > :gap_threshold
             )
            THEN 1 ELSE 0
        END AS low_visibility_episode_start,
        CASE
            WHEN previous_timestamp IS NOT NULL
             AND timestamp - previous_timestamp > :gap_threshold
            THEN 1 ELSE 0
        END AS discontinuity,
        CASE
            WHEN previous_timestamp IS NULL THEN NULL
            ELSE timestamp - previous_timestamp
        END AS interval_seconds
    FROM ordered
)
"""

_SUMMARY_SELECT = """
    COUNT(*) AS sample_count,
    COALESCE(SUM(weight_seconds), 0) AS estimated_observed_seconds,
    AVG(face_ratio) AS sample_average_face_ratio,
    SUM(face_ratio * weight_seconds) / NULLIF(SUM(weight_seconds), 0)
        AS time_weighted_average_face_ratio,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY face_ratio)
        AS median_face_ratio,
    percentile_cont(0.1) WITHIN GROUP (ORDER BY face_ratio)
        AS p10_face_ratio,
    percentile_cont(0.9) WITHIN GROUP (ORDER BY face_ratio)
        AS p90_face_ratio,
    stddev_pop(face_ratio) AS face_ratio_standard_deviation,
    MIN(face_ratio) AS minimum_face_ratio,
    MAX(face_ratio) AS maximum_face_ratio,
    COUNT(*) FILTER (WHERE alarm_active IS TRUE) AS alarm_sample_count,
    COUNT(*) FILTER (WHERE face_ratio = 0) AS no_face_sample_count,
    COUNT(*) FILTER (WHERE face_ratio < :low_visibility_threshold)
        AS low_visibility_sample_count,
    COUNT(*) FILTER (WHERE face_ratio >= :high_visibility_threshold)
        AS high_visibility_sample_count,
    COUNT(*) FILTER (WHERE has_visible_center) AS visible_center_sample_count,
    COUNT(*) FILTER (WHERE has_invalid_center) AS invalid_center_sample_count,
    AVG(face_center_x) FILTER (WHERE has_visible_center)
        AS average_face_center_x,
    AVG(face_center_y) FILTER (WHERE has_visible_center)
        AS average_face_center_y,
    AVG(face_center_x::double precision / :image_width)
        FILTER (WHERE has_visible_center) AS normalized_center_x,
    AVG(face_center_y::double precision / :image_height)
        FILTER (WHERE has_visible_center) AS normalized_center_y,
    stddev_pop(face_center_x::double precision / :image_width)
        FILTER (WHERE has_visible_center)
        AS normalized_center_x_standard_deviation,
    stddev_pop(face_center_y::double precision / :image_height)
        FILTER (WHERE has_visible_center)
        AS normalized_center_y_standard_deviation,
    COUNT(*) FILTER (
        WHERE has_visible_center
          AND (
            face_center_x < :edge_left
            OR face_center_x > :edge_right
            OR face_center_y < :edge_top
            OR face_center_y > :edge_bottom
          )
    ) AS edge_center_sample_count,
    COALESCE(SUM(alarm_episode_start), 0) AS alarm_episode_count,
    COALESCE(SUM(no_face_episode_start), 0) AS no_face_episode_count,
    COALESCE(SUM(low_visibility_episode_start), 0)
        AS low_visibility_episode_count,
    COALESCE(SUM(weight_seconds) FILTER (WHERE alarm_active IS TRUE), 0)
        AS estimated_alarm_seconds,
    COALESCE(SUM(weight_seconds) FILTER (WHERE face_ratio = 0), 0)
        AS estimated_no_face_seconds,
    COALESCE(
        SUM(weight_seconds) FILTER (
            WHERE face_ratio < :low_visibility_threshold
        ),
        0
    ) AS estimated_low_visibility_seconds,
    COALESCE(
        SUM(weight_seconds) FILTER (
            WHERE face_ratio >= :high_visibility_threshold
        ),
        0
    ) AS estimated_high_visibility_seconds,
    COALESCE(SUM(discontinuity), 0) AS discontinuity_count,
    MAX(interval_seconds) FILTER (WHERE interval_seconds > 0)
        AS longest_interval_seconds
"""

_DAILY_SUMMARY_QUERY = (
    _COMMON_CTE
    + "SELECT local_day,"
    + _SUMMARY_SELECT
    + " FROM prepared GROUP BY local_day ORDER BY local_day"
)

_PERIOD_SUMMARY_QUERY = _COMMON_CTE + "SELECT" + _SUMMARY_SELECT + " FROM prepared"

_EVENT_QUERY = """
WITH ordered AS (
    SELECT
        id,
        timestamp,
        face_ratio,
        alarm_active,
        LAG(timestamp) OVER (ORDER BY timestamp, id) AS previous_timestamp,
        LEAD(timestamp) OVER (ORDER BY timestamp, id) AS next_timestamp,
        LAG(alarm_active) OVER (ORDER BY timestamp, id) AS previous_alarm_active,
        LAG(face_ratio) OVER (ORDER BY timestamp, id) AS previous_face_ratio
    FROM monitoring_records
    WHERE user_id = :user_id
      AND timestamp >= :start_timestamp
      AND timestamp <= :end_timestamp
), marked AS (
    SELECT
        *,
        LEAST(
            GREATEST(
                COALESCE(
                    next_timestamp - timestamp,
                    LEAST(
                        GREATEST(:end_timestamp - timestamp, 0),
                        :nominal_interval
                    )
                ),
                0
            ),
            :state_hold_cap
        )::double precision AS weight_seconds,
        CASE
            WHEN alarm_active IS TRUE
             AND (
                previous_alarm_active IS NOT TRUE
                OR previous_timestamp IS NULL
                OR timestamp - previous_timestamp > :gap_threshold
             )
            THEN 1 ELSE 0
        END AS alarm_start,
        CASE
            WHEN face_ratio = 0
             AND (
                previous_face_ratio IS NULL
                OR previous_face_ratio <> 0
                OR previous_timestamp IS NULL
                OR timestamp - previous_timestamp > :gap_threshold
             )
            THEN 1 ELSE 0
        END AS no_face_start,
        CASE
            WHEN face_ratio < :low_visibility_threshold
             AND (
                previous_face_ratio IS NULL
                OR previous_face_ratio >= :low_visibility_threshold
                OR previous_timestamp IS NULL
                OR timestamp - previous_timestamp > :gap_threshold
             )
            THEN 1 ELSE 0
        END AS low_visibility_start
    FROM ordered
), grouped AS (
    SELECT
        *,
        SUM(alarm_start) OVER (ORDER BY timestamp, id) AS alarm_group,
        SUM(no_face_start) OVER (ORDER BY timestamp, id) AS no_face_group,
        SUM(low_visibility_start) OVER (ORDER BY timestamp, id)
            AS low_visibility_group
    FROM marked
), alarm_episodes AS (
    SELECT alarm_group, SUM(weight_seconds) AS duration_seconds
    FROM grouped
    WHERE alarm_active IS TRUE
    GROUP BY alarm_group
), no_face_episodes AS (
    SELECT no_face_group, SUM(weight_seconds) AS duration_seconds
    FROM grouped
    WHERE face_ratio = 0
    GROUP BY no_face_group
), low_visibility_episodes AS (
    SELECT low_visibility_group, SUM(weight_seconds) AS duration_seconds
    FROM grouped
    WHERE face_ratio < :low_visibility_threshold
    GROUP BY low_visibility_group
)
SELECT
    (SELECT COUNT(*) FROM alarm_episodes) AS alarm_episode_count,
    COALESCE((SELECT SUM(duration_seconds) FROM alarm_episodes), 0)
        AS alarm_duration_seconds,
    COALESCE((SELECT MAX(duration_seconds) FROM alarm_episodes), 0)
        AS longest_alarm_episode_seconds,
    (SELECT COUNT(*) FROM no_face_episodes) AS no_face_episode_count,
    COALESCE((SELECT SUM(duration_seconds) FROM no_face_episodes), 0)
        AS no_face_duration_seconds,
    COALESCE((SELECT MAX(duration_seconds) FROM no_face_episodes), 0)
        AS longest_no_face_episode_seconds,
    (SELECT COUNT(*) FROM low_visibility_episodes)
        AS low_visibility_episode_count,
    COALESCE((SELECT SUM(duration_seconds) FROM low_visibility_episodes), 0)
        AS low_visibility_duration_seconds,
    COALESCE((SELECT MAX(duration_seconds) FROM low_visibility_episodes), 0)
        AS longest_low_visibility_episode_seconds
"""
