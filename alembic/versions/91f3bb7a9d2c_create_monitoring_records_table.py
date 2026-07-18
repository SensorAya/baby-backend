"""create monitoring records table

Revision ID: 91f3bb7a9d2c
Revises: f5a83e9faffa
Create Date: 2026-07-18

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "91f3bb7a9d2c"
down_revision: Union[str, Sequence[str], None] = "f5a83e9faffa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the monitoring records table."""
    op.create_table(
        "monitoring_records",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("timestamp", sa.BigInteger(), nullable=False),
        sa.Column("face_ratio", sa.Integer(), nullable=False),
        sa.Column("face_center_x", sa.Integer(), nullable=False),
        sa.Column("face_center_y", sa.Integer(), nullable=False),
        sa.Column(
            "alarm_active",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "face_center_x >= 0",
            name="ck_monitoring_records_face_center_x",
        ),
        sa.CheckConstraint(
            "face_center_y >= 0",
            name="ck_monitoring_records_face_center_y",
        ),
        sa.CheckConstraint(
            "face_ratio BETWEEN 0 AND 100",
            name="ck_monitoring_records_face_ratio",
        ),
        sa.CheckConstraint(
            "timestamp >= 0",
            name="ck_monitoring_records_timestamp",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_monitoring_records_user_id"),
        "monitoring_records",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_monitoring_records_timestamp"),
        "monitoring_records",
        ["timestamp"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the monitoring records table."""
    op.drop_index(
        op.f("ix_monitoring_records_timestamp"),
        table_name="monitoring_records",
    )
    op.drop_index(
        op.f("ix_monitoring_records_user_id"),
        table_name="monitoring_records",
    )
    op.drop_table("monitoring_records")
