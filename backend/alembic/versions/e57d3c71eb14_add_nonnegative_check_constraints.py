"""add_nonnegative_check_constraints

Revision ID: e57d3c71eb14
Revises: 9e35486cd757
Create Date: 2026-01-22 00:52:55.406538

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e57d3c71eb14'
down_revision: Union[str, Sequence[str], None] = '9e35486cd757'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint("ck_runs_total_tokens_nonneg", "runs", "total_tokens >= 0")
    op.create_check_constraint("ck_runs_total_cost_nonneg", "runs", "total_cost_usd >= 0")

    op.create_check_constraint("ck_steps_latency_nonneg", "steps", "latency_ms >= 0")
    op.create_check_constraint("ck_steps_tokens_nonneg", "steps", "tokens >= 0")
    op.create_check_constraint("ck_steps_cost_nonneg", "steps", "cost_usd >= 0")



def downgrade() -> None:
    op.drop_constraint("ck_steps_cost_nonneg", "steps", type_="check")
    op.drop_constraint("ck_steps_tokens_nonneg", "steps", type_="check")
    op.drop_constraint("ck_steps_latency_nonneg", "steps", type_="check")

    op.drop_constraint("ck_runs_total_cost_nonneg", "runs", type_="check")
    op.drop_constraint("ck_runs_total_tokens_nonneg", "runs", type_="check")
