"""create payroll table

Revision ID: a8a5167c01ca
Revises: d7e4f1c3a2b0
Create Date: 2026-07-09 17:16:40.330329

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8a5167c01ca'
down_revision: Union[str, Sequence[str], None] = 'd7e4f1c3a2b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite batch mode recreates the table. We must ensure the old
    # ck_payroll_bonuses_non_negative constraint (which references the
    # soon-to-be-dropped 'bonuses' column) is replaced by the new
    # ck_payroll_bonus_non_negative / ck_payroll_allowance_non_negative
    # constraints.  We do everything in a single batch block so SQLite
    # can recreate the table in one step.
    with op.batch_alter_table('payroll', schema=None) as batch_op:
        # --- new columns ---
        batch_op.add_column(sa.Column('org_id', sa.Integer(), nullable=False))
        batch_op.add_column(sa.Column('overtime_hours', sa.Numeric(precision=5, scale=1), server_default=sa.text('0'), nullable=False))
        batch_op.add_column(sa.Column('bonus', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
        batch_op.add_column(sa.Column('allowance', sa.Numeric(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
        batch_op.add_column(sa.Column('status', sa.String(length=15), server_default=sa.text("'pending'"), nullable=False))
        batch_op.add_column(sa.Column('notes', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False))
        batch_op.add_column(sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False))

        # --- constraints ---
        batch_op.create_index(batch_op.f('ix_payroll_org_id'), ['org_id'], unique=False)
        batch_op.create_foreign_key(
            batch_op.f('fk_payroll_org_id_organizations'),
            'organizations', ['org_id'], ['id'],
            ondelete='CASCADE',
        )

        # Drop old check constraints that reference the 'bonuses' column so that
        # the table recreation does not carry them forward.
        batch_op.drop_constraint('ck_payroll_bonuses_non_negative', type_='check')

        # --- drop old column ---
        batch_op.drop_column('bonuses')

    # Re-add the replacement check constraints after the batch block so they
    # are applied to the newly-shaped table (separate ALTER).
    with op.batch_alter_table('payroll', schema=None) as batch_op:
        batch_op.create_check_constraint('ck_payroll_bonus_non_negative',     sa.text('bonus >= 0'))
        batch_op.create_check_constraint('ck_payroll_allowance_non_negative', sa.text('allowance >= 0'))
        batch_op.create_check_constraint('ck_payroll_overtime_hours_non_negative', sa.text('overtime_hours >= 0'))
        batch_op.create_check_constraint('ck_payroll_valid_status',            sa.text("status IN ('pending','paid','cancelled')"))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('payroll', schema=None) as batch_op:
        batch_op.drop_constraint('ck_payroll_valid_status',            type_='check')
        batch_op.drop_constraint('ck_payroll_overtime_hours_non_negative', type_='check')
        batch_op.drop_constraint('ck_payroll_allowance_non_negative',  type_='check')
        batch_op.drop_constraint('ck_payroll_bonus_non_negative',      type_='check')

    with op.batch_alter_table('payroll', schema=None) as batch_op:
        batch_op.add_column(sa.Column('bonuses', sa.NUMERIC(precision=12, scale=2), server_default=sa.text('0'), nullable=False))
        batch_op.drop_constraint(batch_op.f('fk_payroll_org_id_organizations'), type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_payroll_org_id'))
        batch_op.drop_column('updated_at')
        batch_op.drop_column('created_at')
        batch_op.drop_column('notes')
        batch_op.drop_column('status')
        batch_op.drop_column('allowance')
        batch_op.drop_column('bonus')
        batch_op.drop_column('overtime_hours')
        batch_op.drop_column('org_id')
        batch_op.create_check_constraint('ck_payroll_bonuses_non_negative', sa.text('bonuses >= 0'))