"""baseline schema

Adds the user_stats table (points, streaks, solved counters).

All other tables were created historically by ``app.db.init_db`` and the
Spider ingest pipeline; this baseline covers the first Alembic-managed
change.  Fresh deployments run migrations from scratch plus init_db's
``create_all`` bootstrap, so stale diffs are intentionally excluded here.

Revision ID: e45be3e3d411
Revises:
Create Date: 2026-10-21 01:39:38.788242

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e45be3e3d411'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('user_stats',
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('total_points', sa.Integer(), nullable=False),
        sa.Column('easy_solved', sa.Integer(), nullable=False),
        sa.Column('medium_solved', sa.Integer(), nullable=False),
        sa.Column('hard_solved', sa.Integer(), nullable=False),
        sa.Column('extra_solved', sa.Integer(), nullable=False),
        sa.Column('current_streak', sa.Integer(), nullable=False),
        sa.Column('longest_streak', sa.Integer(), nullable=False),
        sa.Column('last_daily_solved_date', sa.Date(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('user_stats')
