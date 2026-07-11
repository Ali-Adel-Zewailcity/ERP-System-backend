"""merge sales and payroll branches

Revision ID: f5bc91121326
Revises: 44185db38151, b7c3d9e4f5a6
Create Date: 2026-07-11 20:59:31.731719

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f5bc91121326'
down_revision: Union[str, Sequence[str], None] = ('44185db38151', 'b7c3d9e4f5a6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
