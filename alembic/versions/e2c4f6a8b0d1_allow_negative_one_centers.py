"""allow negative one monitoring center coordinates

Revision ID: e2c4f6a8b0d1
Revises: d4e5f6a7b8c9
Create Date: 2026-07-23

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2c4f6a8b0d1"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CENTER_COLUMNS = (
    "face_center_x",
    "face_center_y",
    "baby_center_x",
    "baby_center_y",
)


def upgrade() -> None:
    """Use -1 as the persisted sentinel for an undetected center."""
    for column in _CENTER_COLUMNS:
        op.drop_constraint(
            f"ck_monitoring_records_{column}",
            "monitoring_records",
            type_="check",
        )
        op.create_check_constraint(
            f"ck_monitoring_records_{column}",
            "monitoring_records",
            f"{column} >= -1",
        )

    op.execute(
        """
        UPDATE monitoring_records
        SET face_center_x = -1, face_center_y = -1
        WHERE face_center_x = 0
          AND face_center_y = 0
          AND face_ratio = 0
        """
    )
    for column in ("baby_center_x", "baby_center_y"):
        op.alter_column(
            "monitoring_records",
            column,
            existing_type=sa.Integer(),
            existing_nullable=False,
            server_default=sa.text("-1"),
        )
    op.execute(
        """
        UPDATE monitoring_records
        SET baby_center_x = -1, baby_center_y = -1
        WHERE baby_center_x = 0
          AND baby_center_y = 0
          AND baby_ratio = 0
        """
    )


def downgrade() -> None:
    """Restore non-negative center constraints and the former zero sentinel."""
    for column in _CENTER_COLUMNS:
        op.drop_constraint(
            f"ck_monitoring_records_{column}",
            "monitoring_records",
            type_="check",
        )

    op.execute(
        """
        UPDATE monitoring_records
        SET
            face_center_x = GREATEST(face_center_x, 0),
            face_center_y = GREATEST(face_center_y, 0),
            baby_center_x = GREATEST(baby_center_x, 0),
            baby_center_y = GREATEST(baby_center_y, 0)
        """
    )
    for column in ("baby_center_x", "baby_center_y"):
        op.alter_column(
            "monitoring_records",
            column,
            existing_type=sa.Integer(),
            existing_nullable=False,
            server_default=sa.text("0"),
        )

    for column in _CENTER_COLUMNS:
        op.create_check_constraint(
            f"ck_monitoring_records_{column}",
            "monitoring_records",
            f"{column} >= 0",
        )
