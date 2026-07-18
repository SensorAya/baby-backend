"""add monitoring report composite index

Revision ID: c3f7a9b12d44
Revises: 91f3bb7a9d2c
Create Date: 2026-07-18

"""

from typing import Sequence, Union

from alembic import op

revision: str = "c3f7a9b12d44"
down_revision: Union[str, Sequence[str], None] = "91f3bb7a9d2c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Speed up per-user time-window scans and deterministic ordering."""
    op.create_index(
        "ix_monitoring_records_user_timestamp_id",
        "monitoring_records",
        ["user_id", "timestamp", "id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove the report query index."""
    op.drop_index(
        "ix_monitoring_records_user_timestamp_id",
        table_name="monitoring_records",
    )
