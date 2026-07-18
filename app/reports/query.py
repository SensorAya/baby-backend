from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import Date, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monitoring_record import MonitoringRecord

REPORT_TIMEZONE = "Asia/Taipei"
MIN_REPORT_DAYS = 1
MAX_REPORT_DAYS = 30


@dataclass(frozen=True, slots=True)
class DailyMonitoringSummary:
    day: date
    sample_count: int
    average_face_ratio: float | None
    minimum_face_ratio: int | None
    maximum_face_ratio: int | None
    alarm_sample_count: int
    no_face_sample_count: int
    visible_center_sample_count: int
    average_face_center_x: float | None
    average_face_center_y: float | None


@dataclass(frozen=True, slots=True)
class MonitoringReportData:
    days: int
    timezone_name: str
    start_at: datetime
    end_at: datetime
    daily: tuple[DailyMonitoringSummary, ...]

    @property
    def total_sample_count(self) -> int:
        return sum(summary.sample_count for summary in self.daily)


async def query_monitoring_report_data(
    db: AsyncSession,
    user_id: UUID,
    days: int,
    *,
    now: datetime | None = None,
) -> MonitoringReportData:
    """Query one user's monitoring summaries for recent local calendar days."""
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

    local_day = cast(
        func.timezone(
            REPORT_TIMEZONE,
            func.to_timestamp(MonitoringRecord.timestamp),
        ),
        Date,
    ).label("day")
    has_visible_center = (MonitoringRecord.face_center_x != 0) | (
        MonitoringRecord.face_center_y != 0
    )

    statement = (
        select(
            local_day,
            func.count().label("sample_count"),
            func.avg(MonitoringRecord.face_ratio).label("average_face_ratio"),
            func.min(MonitoringRecord.face_ratio).label("minimum_face_ratio"),
            func.max(MonitoringRecord.face_ratio).label("maximum_face_ratio"),
            func.sum(
                case((MonitoringRecord.alarm_active.is_(True), 1), else_=0)
            ).label("alarm_sample_count"),
            func.sum(case((MonitoringRecord.face_ratio == 0, 1), else_=0)).label(
                "no_face_sample_count"
            ),
            func.sum(case((has_visible_center, 1), else_=0)).label(
                "visible_center_sample_count"
            ),
            func.avg(
                case((has_visible_center, MonitoringRecord.face_center_x))
            ).label("average_face_center_x"),
            func.avg(
                case((has_visible_center, MonitoringRecord.face_center_y))
            ).label("average_face_center_y"),
        )
        .where(
            MonitoringRecord.user_id == user_id,
            MonitoringRecord.timestamp >= int(start_at.timestamp()),
            MonitoringRecord.timestamp <= int(end_at.timestamp()),
        )
        .group_by(local_day)
        .order_by(local_day)
    )

    result = await db.execute(statement)
    summaries_by_day = {
        row["day"]: DailyMonitoringSummary(
            day=row["day"],
            sample_count=int(row["sample_count"]),
            average_face_ratio=_optional_float(row["average_face_ratio"]),
            minimum_face_ratio=_optional_int(row["minimum_face_ratio"]),
            maximum_face_ratio=_optional_int(row["maximum_face_ratio"]),
            alarm_sample_count=int(row["alarm_sample_count"] or 0),
            no_face_sample_count=int(row["no_face_sample_count"] or 0),
            visible_center_sample_count=int(
                row["visible_center_sample_count"] or 0
            ),
            average_face_center_x=_optional_float(row["average_face_center_x"]),
            average_face_center_y=_optional_float(row["average_face_center_y"]),
        )
        for row in result.mappings().all()
    }

    daily = tuple(
        summaries_by_day.get(day, _empty_daily_summary(day))
        for day in (start_day + timedelta(days=offset) for offset in range(days))
    )
    return MonitoringReportData(
        days=days,
        timezone_name=REPORT_TIMEZONE,
        start_at=start_at,
        end_at=end_at,
        daily=daily,
    )


def format_monitoring_report_data(data: MonitoringReportData) -> str:
    """Convert aggregated monitoring data into compact LLM-ready text."""
    report_timezone = ZoneInfo(data.timezone_name)
    start_local = data.start_at.astimezone(report_timezone)
    end_local = data.end_at.astimezone(report_timezone)
    lines = [
        "Baby monitoring report data",
        f"Timezone: {data.timezone_name}",
        f"Period ({data.timezone_name}): "
        f"{start_local.isoformat()} to {end_local.isoformat()}",
        f"Days: {data.days}",
        f"Total samples: {data.total_sample_count}",
        "",
        "Daily summaries:",
    ]

    for summary in data.daily:
        if summary.sample_count == 0:
            lines.append(f"- {summary.day.isoformat()}: no data")
            continue

        alarm_percentage = summary.alarm_sample_count / summary.sample_count * 100
        no_face_percentage = (
            summary.no_face_sample_count / summary.sample_count * 100
        )
        center = "unavailable"
        if (
            summary.average_face_center_x is not None
            and summary.average_face_center_y is not None
        ):
            center = (
                f"({summary.average_face_center_x:.1f}, "
                f"{summary.average_face_center_y:.1f}) from "
                f"{summary.visible_center_sample_count} visible samples"
            )

        lines.append(
            f"- {summary.day.isoformat()}: samples={summary.sample_count}; "
            f"face_ratio avg/min/max="
            f"{summary.average_face_ratio:.1f}/"
            f"{summary.minimum_face_ratio}/"
            f"{summary.maximum_face_ratio}; "
            f"alarm samples={summary.alarm_sample_count} "
            f"({alarm_percentage:.1f}%); "
            f"no-face samples={summary.no_face_sample_count} "
            f"({no_face_percentage:.1f}%); "
            f"average visible center={center}"
        )

    lines.extend(
        [
            "",
            "Field semantics:",
            "- face_ratio: percentage of frames containing a face in the prior "
            "10-second sliding window.",
            "- alarm samples: samples where alarm_active was true; this is not "
            "a measured alarm duration.",
            "- face center: latest detected face center in a 1280x720 image; "
            "(0, 0) means no face and is excluded from center averages.",
        ]
    )
    return "\n".join(lines)


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


def _empty_daily_summary(day: date) -> DailyMonitoringSummary:
    return DailyMonitoringSummary(
        day=day,
        sample_count=0,
        average_face_ratio=None,
        minimum_face_ratio=None,
        maximum_face_ratio=None,
        alarm_sample_count=0,
        no_face_sample_count=0,
        visible_center_sample_count=0,
        average_face_center_x=None,
        average_face_center_y=None,
    )


def _optional_float(value: object) -> float | None:
    return None if value is None else float(value)


def _optional_int(value: object) -> int | None:
    return None if value is None else int(value)
