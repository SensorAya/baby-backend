# baby-backend

A FastAPI backend for complete baby-monitoring sessions, real-time alarm delivery,
and LLM-assisted single-session, daily, weekly, or monthly reports.

## Heartbeats and complete sessions

`POST /api/monitoring` is Bearer-authenticated and accepts:

```json
{
  "timestamp": 1752001234,
  "face_ratio": 85,
  "face_center_x": 640,
  "face_center_y": 360,
  "event": "start",
  "baby_center_x": 640,
  "baby_center_y": 360,
  "baby_ratio": 85,
  "activity_level": 24
}
```

`event` is required but nullable: `start`, `stop`, or `null`. A user can have only
one active session. `start` opens it, ordinary heartbeats join it, and `stop`
completes it. Heartbeats outside an active session return `409`.

Each `face_center_*` or `baby_center_*` coordinate accepts `-1` when that target
does not exist in the frame. Non-negative coordinates, including `(0, 0)`, are
treated as detected positions.

`activity_level` is an edge-computed `0..100` value based on the 30-frame average
of adjacent baby bounding-box center displacement. Its engineering bands are:
`<10` stationary, `10..30` minor movement, and `>30` major movement.

`GET /api/monitoring/history?period=session|daily|weekly|monthly` returns paginated
aggregates. Only complete `start -> stop` sessions are included, and calendar
groups are based on `Asia/Taipei` session start time.

## Real-time alarms

`POST /api/alarms` accepts the authenticated device transition:

```json
{
  "timestamp": 1752000660,
  "event": "triggered",
  "face_ratio": 20,
  "baby_ratio": 20
}
```

`event` is `triggered` or `cleared`. `GET /api/alarms/active` restores the latest
state. Apps connect to `WS /api/alarms/ws` with either an `Authorization: Bearer`
header or WebSocket subprotocols `["bearer", token]`; the server sends an initial
`state` message and subsequent `alarm` messages. The current broker is process
local, so production multi-worker deployments should replace it with shared
pub/sub (for example PostgreSQL LISTEN/NOTIFY or Redis).

## Monitoring report pipeline

`POST /api/reports` accepts `session`, `daily`, `weekly`, or `monthly`. For
`session`, `session_id` is optional and defaults to the latest completed session.
The backend derives report facts before invoking the LLM instead of asking the
model to reason from a few raw averages.

The analysis includes:

- local-calendar-day aggregation in `Asia/Taipei`;
- sampling quality: first/last sample, median and P90 interval, duplicate timestamps, long discontinuities, and estimated observation support;
- time-weighted face visibility with a capped state-hold interval, alongside sample mean, median, P10/P90, and standard deviation;
- operational low-visibility (`face_ratio < 20`) and high-visibility (`face_ratio >= 80`) metrics;
- independent alarm, no-face, and low-visibility episode segmentation with estimated total and longest duration;
- robust Theil–Sen trend estimation using only days with enough samples and relative observation support;
- normalized face-center position, dispersion, edge frequency, and invalid coordinate detection.
- time-weighted activity level and stationary/minor/major movement bands.

The LLM receives structured JSON plus explicit evidence boundaries. Engineering thresholds are not medical or safety thresholds, estimated durations are not exact, and observation support must not be described as device uptime.

## Apply the database index

```bash
uv run alembic upgrade head
```

Migrations add complete monitoring sessions, activity levels, alarm events, and
the indexes used by history and report scans.

## Verification

```bash
uv run ruff check app alembic tests
uv run python -m unittest discover -s tests -v
```
