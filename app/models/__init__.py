from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Import all models here so Alembic can discover them via Base.metadata
from app.models.api_token import ApiToken  # noqa: F401, E402
from app.models.monitoring_record import MonitoringRecord  # noqa: F401, E402
from app.models.user import User  # noqa: F401, E402

__all__ = ["ApiToken", "Base", "MonitoringRecord", "User"]
