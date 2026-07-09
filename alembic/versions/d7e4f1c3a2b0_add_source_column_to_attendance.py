"""add_source_column_to_attendance

Revision ID: d7e4f1c3a2b0
Revises: ae37784bd780
Create Date: 2026-07-09 00:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7e4f1c3a2b0'
down_revision: Union[str, Sequence[str], None] = 'ae37784bd780'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('attendance', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('source', sa.String(length=20), nullable=False,
                      server_default=sa.text("'manual'"))
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('attendance', schema=None) as batch_op:
        batch_op.drop_column('source')
