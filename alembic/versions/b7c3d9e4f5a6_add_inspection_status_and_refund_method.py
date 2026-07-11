"""add inspection_status and refund_method to return_items

Revision ID: b7c3d9e4f5a6
Revises: 44185db38151
Create Date: 2026-07-11 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c3d9e4f5a6'
down_revision: Union[str, Sequence[str], None] = 'd7e4f1c3a2b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('return_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('inspection_status', sa.String(10), nullable=True))
        batch_op.add_column(sa.Column('refund_method', sa.String(20), nullable=True))
        batch_op.create_check_constraint(
            constraint_name='ck_return_items_inspection_status',
            condition=sa.text("inspection_status IS NULL OR inspection_status IN ('pass','fail')"),
        )
        batch_op.create_check_constraint(
            constraint_name='ck_return_items_refund_method',
            condition=sa.text("refund_method IS NULL OR refund_method IN ('cash','bank_transfer','credit_note','replace')"),
        )


def downgrade() -> None:
    with op.batch_alter_table('return_items', schema=None) as batch_op:
        batch_op.drop_constraint('ck_return_items_inspection_status', type_='check')
        batch_op.drop_constraint('ck_return_items_refund_method', type_='check')
        batch_op.drop_column('inspection_status')
        batch_op.drop_column('refund_method')
