import asyncio
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alarms.broker import alarm_broker
from app.alarms.schemas import (
    AlarmEventCreate,
    AlarmEventResponse,
    AlarmStateResponse,
    AlarmStreamMessage,
    AlarmTransition,
)
from app.auth.dependencies import authenticate_token, get_current_user
from app.core.database import get_db
from app.models.alarm_event import AlarmEvent
from app.models.monitoring_session import MonitoringSession
from app.models.user import User

router = APIRouter(prefix="/api/alarms", tags=["alarms"])


async def _latest_alarm(
    db: AsyncSession,
    user_id: UUID,
) -> AlarmEvent | None:
    return (
        await db.execute(
            select(AlarmEvent)
            .where(AlarmEvent.user_id == user_id)
            .order_by(AlarmEvent.timestamp.desc(), AlarmEvent.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


def _state_message(alarm: AlarmEvent | None, message_type: str) -> dict[str, object]:
    response = AlarmEventResponse.model_validate(alarm) if alarm is not None else None
    return AlarmStreamMessage(
        type=message_type,
        active=alarm is not None and alarm.event == AlarmTransition.TRIGGERED,
        alarm=response,
    ).model_dump(mode="json")


@router.get("/active", response_model=AlarmStateResponse)
async def get_active_alarm(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AlarmStateResponse:
    """Return the user's latest persisted alarm state."""
    alarm = await _latest_alarm(db, current_user.id)
    return AlarmStateResponse(
        active=alarm is not None and alarm.event == AlarmTransition.TRIGGERED,
        alarm=alarm,
    )


@router.post(
    "",
    response_model=AlarmEventResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_alarm_event(
    body: AlarmEventCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AlarmEvent:
    """Persist an alarm transition and immediately fan it out to this user's app."""
    matching_session = (
        await db.execute(
            select(MonitoringSession)
            .where(
                MonitoringSession.user_id == current_user.id,
                MonitoringSession.started_at <= body.timestamp,
                (
                    MonitoringSession.ended_at.is_(None)
                    | (MonitoringSession.ended_at >= body.timestamp)
                ),
            )
            .order_by(MonitoringSession.started_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    alarm = AlarmEvent(
        user_id=current_user.id,
        session_id=matching_session.id if matching_session is not None else None,
        **body.model_dump(),
    )
    db.add(alarm)
    await db.commit()
    await db.refresh(alarm)
    latest = await _latest_alarm(db, current_user.id)
    await alarm_broker.publish(
        current_user.id,
        _state_message(latest, "alarm"),
    )
    return alarm


@router.websocket("/ws")
async def alarm_websocket(
    websocket: WebSocket,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Deliver persisted state plus live alarm transitions over an authenticated WS."""
    raw_token, subprotocol = _websocket_token(websocket)
    if raw_token is None:
        await websocket.close(code=4401, reason="Missing Bearer token")
        return
    try:
        user = await authenticate_token(raw_token, db)
    except HTTPException:
        await websocket.close(code=4401, reason="Invalid Bearer token")
        return

    await websocket.accept(subprotocol=subprotocol)
    try:
        async with alarm_broker.subscribe(user.id) as queue:
            latest = await _latest_alarm(db, user.id)
            await websocket.send_json(_state_message(latest, "state"))
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=25)
                except TimeoutError:
                    message = {"type": "ping"}
                await websocket.send_json(message)
    except WebSocketDisconnect:
        return


def _websocket_token(websocket: WebSocket) -> tuple[str | None, str | None]:
    authorization = websocket.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer" and token:
        return token, None

    protocols = [
        item.strip()
        for item in websocket.headers.get("sec-websocket-protocol", "").split(",")
        if item.strip()
    ]
    if len(protocols) >= 2 and protocols[0].lower() == "bearer":
        return protocols[1], protocols[0]
    return None, None


__all__ = ["router"]
