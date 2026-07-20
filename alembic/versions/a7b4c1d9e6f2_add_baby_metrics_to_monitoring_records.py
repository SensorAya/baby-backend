"""add baby metrics to monitoring records

Revision ID: a7b4c1d9e6f2
Revises: c3f7a9b12d44
Create Date: 2026-07-20

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a7b4c1d9e6f2"
down_revision: Union[str, Sequence[str], None] = "c3f7a9b12d44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add persisted baby detection metrics to monitoring records."""
    op.add_column(
        "monitoring_records",
        sa.Column(
            "baby_center_x",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "monitoring_records",
        sa.Column(
            "baby_center_y",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "monitoring_records",
        sa.Column(
            "baby_ratio",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_monitoring_records_baby_center_x",
        "monitoring_records",
        "baby_center_x >= 0",
    )
    op.create_check_constraint(
        "ck_monitoring_records_baby_center_y",
        "monitoring_records",
        "baby_center_y >= 0",
    )
    op.create_check_constraint(
        "ck_monitoring_records_baby_ratio",
        "monitoring_records",
        "baby_ratio BETWEEN 0 AND 100",
    )


def downgrade() -> None:
    """Remove persisted baby detection metrics from monitoring records."""
    op.drop_constraint(
        "ck_monitoring_records_baby_ratio",
        "monitoring_records",
        type_="check",
    )
    op.drop_constraint(
        "ck_monitoring_records_baby_center_y",
        "monitoring_records",
        type_="check",
    )
    op.drop_constraint(
        "ck_monitoring_records_baby_center_x",
        "monitoring_records",
        type_="check",
    )
    op.drop_column("monitoring_records", "baby_ratio")
    op.drop_column("monitoring_records", "baby_center_y")
    op.drop_column("monitoring_records", "baby_center_x")
