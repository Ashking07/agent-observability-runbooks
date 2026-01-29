"""add policy_id to run_validations

Revision ID: 111b3e8dd99a
Revises: e9cd649a50d7
Create Date: 2026-01-29 03:35:33.044292
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "111b3e8dd99a"
down_revision: Union[str, Sequence[str], None] = "e9cd649a50d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add columns
    op.add_column(
        "run_validations",
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "run_validations",
        sa.Column("policy_name", sa.String(length=255), nullable=True),
    )

    # Add FK with a real name + safe delete behavior
    op.create_foreign_key(
        "fk_run_validations_policy_id_policies",
        "run_validations",
        "policies",
        ["policy_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_run_validations_policy_id_policies",
        "run_validations",
        type_="foreignkey",
    )
    op.drop_column("run_validations", "policy_name")
    op.drop_column("run_validations", "policy_id")
