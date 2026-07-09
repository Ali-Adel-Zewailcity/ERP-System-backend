"""fix payroll constraint name prefixes

Revision ID: 44185db38151
Revises: a8a5167c01ca
Create Date: 2026-07-09 17:24:52.520284

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '44185db38151'
down_revision: Union[str, Sequence[str], None] = 'a8a5167c01ca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite cannot rename constraints; recreate the table with clean names.
    op.execute("""
CREATE TABLE payroll_new (
    id              INTEGER       NOT NULL  PRIMARY KEY,
    employee_id     INTEGER       NOT NULL,
    month           SMALLINT      NOT NULL,
    year            SMALLINT      NOT NULL,
    days_worked     INTEGER       DEFAULT 0 NOT NULL,
    absences        INTEGER       DEFAULT 0 NOT NULL,
    deductions      NUMERIC(12,2) DEFAULT 0 NOT NULL,
    gross_salary    NUMERIC(12,2) NOT NULL,
    net_salary      NUMERIC(12,2) NOT NULL,
    generated_at    DATETIME      DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
    org_id          INTEGER       NOT NULL,
    overtime_hours  NUMERIC(5,1)  DEFAULT 0 NOT NULL,
    bonus           NUMERIC(12,2) DEFAULT 0 NOT NULL,
    allowance       NUMERIC(12,2) DEFAULT 0 NOT NULL,
    status          VARCHAR(15)   DEFAULT 'pending' NOT NULL,
    notes           TEXT,
    created_at      DATETIME      DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
    updated_at      DATETIME      DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
    CONSTRAINT fk_payroll_employee_id_employees FOREIGN KEY(employee_id) REFERENCES employees(id) ON DELETE RESTRICT,
    CONSTRAINT fk_payroll_org_id_organizations   FOREIGN KEY(org_id)      REFERENCES organizations(id) ON DELETE CASCADE,
    CONSTRAINT uq_payroll_employee_month_year    UNIQUE(employee_id, month, year),
    CONSTRAINT ck_payroll_valid_month            CHECK(month BETWEEN 1 AND 12),
    CONSTRAINT ck_payroll_valid_year             CHECK(year > 2000),
    CONSTRAINT ck_payroll_days_worked_non_negative       CHECK(days_worked >= 0),
    CONSTRAINT ck_payroll_absences_non_negative          CHECK(absences >= 0),
    CONSTRAINT ck_payroll_overtime_hours_non_negative    CHECK(overtime_hours >= 0),
    CONSTRAINT ck_payroll_bonus_non_negative             CHECK(bonus >= 0),
    CONSTRAINT ck_payroll_allowance_non_negative         CHECK(allowance >= 0),
    CONSTRAINT ck_payroll_deductions_non_negative        CHECK(deductions >= 0),
    CONSTRAINT ck_payroll_gross_non_negative             CHECK(gross_salary >= 0),
    CONSTRAINT ck_payroll_net_non_negative               CHECK(net_salary >= 0),
    CONSTRAINT ck_payroll_valid_status                   CHECK(status IN ('pending','paid','cancelled'))
)
    """)
    # Copy existing data (table is empty in practice, but be safe).
    op.execute("INSERT INTO payroll_new SELECT * FROM payroll")
    op.execute("DROP TABLE payroll")
    op.execute("ALTER TABLE payroll_new RENAME TO payroll")


def downgrade() -> None:
    # Recreate the table with the old doubled constraint names (no data risk).
    op.execute("""
CREATE TABLE payroll_old (
    id              INTEGER       NOT NULL  PRIMARY KEY,
    employee_id     INTEGER       NOT NULL,
    month           SMALLINT      NOT NULL,
    year            SMALLINT      NOT NULL,
    days_worked     INTEGER       DEFAULT 0  NOT NULL,
    absences        INTEGER       DEFAULT 0  NOT NULL,
    deductions      NUMERIC(12,2) DEFAULT 0  NOT NULL,
    gross_salary    NUMERIC(12,2) NOT NULL,
    net_salary      NUMERIC(12,2) NOT NULL,
    generated_at    DATETIME      DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
    org_id          INTEGER       NOT NULL,
    overtime_hours  NUMERIC(5,1)  DEFAULT 0  NOT NULL,
    bonus           NUMERIC(12,2) DEFAULT 0  NOT NULL,
    allowance       NUMERIC(12,2) DEFAULT 0  NOT NULL,
    status          VARCHAR(15)   DEFAULT 'pending' NOT NULL,
    notes           TEXT,
    created_at      DATETIME      DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
    updated_at      DATETIME      DEFAULT (CURRENT_TIMESTAMP) NOT NULL,
    CONSTRAINT fk_payroll_employee_id_employees  FOREIGN KEY(employee_id) REFERENCES employees(id) ON DELETE RESTRICT,
    CONSTRAINT fk_payroll_org_id_organizations    FOREIGN KEY(org_id)      REFERENCES organizations(id) ON DELETE CASCADE,
    CONSTRAINT uq_payroll_employee_month_year     UNIQUE(employee_id, month, year),
    CONSTRAINT ck_payroll_ck_payroll_valid_month            CHECK(month BETWEEN 1 AND 12),
    CONSTRAINT ck_payroll_ck_payroll_valid_year             CHECK(year > 2000),
    CONSTRAINT ck_payroll_ck_payroll_days_worked_non_negative       CHECK(days_worked >= 0),
    CONSTRAINT ck_payroll_ck_payroll_absences_non_negative          CHECK(absences >= 0),
    CONSTRAINT ck_payroll_ck_payroll_overtime_hours_non_negative    CHECK(overtime_hours >= 0),
    CONSTRAINT ck_payroll_ck_payroll_bonus_non_negative             CHECK(bonus >= 0),
    CONSTRAINT ck_payroll_ck_payroll_allowance_non_negative         CHECK(allowance >= 0),
    CONSTRAINT ck_payroll_ck_payroll_deductions_non_negative        CHECK(deductions >= 0),
    CONSTRAINT ck_payroll_ck_payroll_gross_non_negative             CHECK(gross_salary >= 0),
    CONSTRAINT ck_payroll_ck_payroll_net_non_negative               CHECK(net_salary >= 0),
    CONSTRAINT ck_payroll_ck_payroll_valid_status                   CHECK(status IN ('pending','paid','cancelled'))
)
    """)
    op.execute("INSERT INTO payroll_old SELECT * FROM payroll")
    op.execute("DROP TABLE payroll")
    op.execute("ALTER TABLE payroll_old RENAME TO payroll")