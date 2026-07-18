# baby-backend

A FastAPI backend for collecting edge-device baby monitoring metrics and generating LLM-assisted weekly or monthly reports.

## Monitoring report pipeline

`POST /api/reports` accepts `weekly` or `monthly`. The backend now derives report facts before invoking the LLM instead of asking the model to reason from a few raw averages.

The analysis includes:

- local-calendar-day aggregation in `Asia/Taipei`;
- sampling quality: first/last sample, median and P90 interval, duplicate timestamps, long discontinuities, and estimated observation support;
- time-weighted face visibility with a capped state-hold interval, alongside sample mean, median, P10/P90, and standard deviation;
- operational low-visibility (`face_ratio < 20`) and high-visibility (`face_ratio >= 80`) metrics;
- independent alarm, no-face, and low-visibility episode segmentation with estimated total and longest duration;
- robust Theil–Sen trend estimation using only days with enough samples and relative observation support;
- normalized face-center position, dispersion, edge frequency, and invalid coordinate detection.

The LLM receives structured JSON plus explicit evidence boundaries. Engineering thresholds are not medical or safety thresholds, estimated durations are not exact, and observation support must not be described as device uptime.

## Apply the database index

```bash
uv run alembic upgrade head
```

The migration adds a `(user_id, timestamp, id)` index used by report time-window scans and deterministic window-function ordering.

## Verification

```bash
uv run ruff check app alembic tests
uv run python -m unittest discover -s tests -v
```
