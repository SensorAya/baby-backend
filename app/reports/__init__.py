"""Reporting package with lazy exports.

Keeping the router import lazy allows pure report-analysis helpers to be tested without
constructing database and LLM clients or requiring runtime environment variables.
"""

from importlib import import_module
from typing import Any

_QUERY_EXPORTS = {
    "DailyMonitoringSummary",
    "EventSummary",
    "FaceVisibilityTrend",
    "MonitoringReportData",
    "MonitoringSummary",
    "SamplingQualitySummary",
    "format_monitoring_report_data",
    "query_monitoring_report_data",
    "query_monitoring_report_text",
}
_PROMPT_EXPORTS = {"SYSTEM_PROMPT", "build_report_user_prompt"}
_ROUTER_EXPORTS = {
    "MonitoringReportRequest",
    "MonitoringReportResponse",
    "ReportPeriod",
    "generate_monitoring_report",
    "router",
}


def __getattr__(name: str) -> Any:
    if name in _QUERY_EXPORTS:
        return getattr(import_module("app.reports.query"), name)
    if name in _PROMPT_EXPORTS:
        return getattr(import_module("app.reports.prompt"), name)
    if name in _ROUTER_EXPORTS:
        return getattr(import_module("app.reports.routes"), name)
    raise AttributeError(name)


__all__ = sorted(_QUERY_EXPORTS | _PROMPT_EXPORTS | _ROUTER_EXPORTS)
