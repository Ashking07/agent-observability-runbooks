"""add_run_validation_input_hash

Revision ID: 4faf3251f5cc
Revises: cedb180ba24d
Create Date: 2026-01-23 03:28:43.806345

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4faf3251f5cc'
down_revision: Union[str, Sequence[str], None] = 'cedb180ba24d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Add column as NULLABLE first
    op.add_column(
        "run_validations",
        sa.Column("input_hash", sa.String(length=64), nullable=True),
    )

    # 2) Backfill existing rows with a deterministic placeholder hash
    #    (We only need *some* non-null value to satisfy NOT NULL.)
    #    We'll use sha256(run_id || created_at || id) as stable-ish input.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
    op.execute("""
        UPDATE run_validations
        SET input_hash =
            encode(
                digest(
                    run_id::text || '|' || created_at::text || '|' || id::text,
                    'sha256'
                ),
                'hex'
            )
        WHERE input_hash IS NULL;
    """)

    # 3) Now enforce NOT NULL
    op.alter_column("run_validations", "input_hash", nullable=False)

    # 4) Add the unique index
    op.create_index(
        "uq_run_validations_run_id_input_hash",
        "run_validations",
        ["run_id", "input_hash"],
        unique=True,
    )

def downgrade() -> None:
    op.drop_index("uq_run_validations_run_id_input_hash", table_name="run_validations")
    op.drop_column("run_validations", "input_hash")
