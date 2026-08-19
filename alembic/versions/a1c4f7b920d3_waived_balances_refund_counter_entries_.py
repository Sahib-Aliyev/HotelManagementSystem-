"""waived balances, refund counter-entries and revocable sessions

Three findings from the 2026-08-17 review need somewhere to store what used to
be lost:

* `reservations.waived_amount / waived_at / waived_by_id` — checking a guest out
  with money still owed, and cancelling a stay that is already in house, were
  both silent. The amount given up and the manager who gave it up are recorded
  now.
* `payments.refunded_payment_id` — a refund is a new row pointing at the
  settled payment it reverses, instead of an edit that erased it.
  `payments.recorded_by_id` keeps the staff member who took the money.
* `users.token_version` — folded into every token as the `tv` claim and
  re-checked on each request, so signing out revokes the token instead of
  merely dropping the cookie.

Revision ID: a1c4f7b920d3
Revises: 70b2246f01fe
Create Date: 2026-08-19 10:12:44.310522
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'a1c4f7b920d3'
down_revision: str | None = '70b2246f01fe'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


#: (table, column, referenced table) for the three new foreign keys.
FOREIGN_KEY_COLUMNS = [
    ("reservations", "waived_by_id", "users"),
    ("payments", "refunded_payment_id", "payments"),
    ("payments", "recorded_by_id", "users"),
]


def _add_fk_column(table: str, column: str, target: str) -> None:
    """Add a nullable FK column on either dialect.

    Alembic emits the foreign key as a separate ALTER on SQLite, which SQLite
    cannot do — and batch mode would recreate the table from reflection, which
    on SQLite silently drops every CHECK constraint (the non-native enums, the
    check-out-after-check-in rule, `amount > 0`). SQLite does accept an inline
    REFERENCES in ADD COLUMN as long as the column defaults to NULL, so the
    statement is written out by hand there.
    """
    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} INTEGER "
            f"REFERENCES {target}(id) ON DELETE SET NULL"
        )
    else:
        op.add_column(
            table,
            sa.Column(
                column,
                sa.Integer(),
                sa.ForeignKey(f"{target}.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )

    op.add_column(
        "reservations", sa.Column("waived_amount", sa.Numeric(10, 2), nullable=True)
    )
    op.add_column(
        "reservations",
        sa.Column("waived_at", sa.DateTime(timezone=True), nullable=True),
    )

    for table, column, target in FOREIGN_KEY_COLUMNS:
        _add_fk_column(table, column, target)

    op.create_index(
        op.f("ix_payments_refunded_payment_id"),
        "payments",
        ["refunded_payment_id"],
        unique=False,
    )


def downgrade() -> None:
    # Batch mode recreates each table from reflection, and SQLite reflection
    # does not return CHECK constraints — so a downgrade on SQLite loses the
    # non-native enum checks. Acceptable on a rollback path, worth knowing.
    op.drop_index(op.f("ix_payments_refunded_payment_id"), table_name="payments")

    with op.batch_alter_table("payments", schema=None) as batch_op:
        batch_op.drop_column("recorded_by_id")
        batch_op.drop_column("refunded_payment_id")

    with op.batch_alter_table("reservations", schema=None) as batch_op:
        batch_op.drop_column("waived_by_id")
        batch_op.drop_column("waived_at")
        batch_op.drop_column("waived_amount")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("token_version")
