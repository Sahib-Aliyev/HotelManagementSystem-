"""audit of 2026-08-19: booking integrity, invoice sequence, indexes, schema drift

Everything here comes out of the audit recorded in BUGS-TODO.md and
SECURITY-TODO.md. Four separate jobs:

* **Schema drift.** `alembic check` failed: three `ON DELETE SET NULL` clauses
  existed in the models but in no migration, so development (which builds its
  schema with `create_all`) and production (which migrates) had structurally
  different foreign keys — on exactly the columns that record who took the
  money. `payments.recorded_by_id`, `payments.refunded_payment_id` and
  `reservations.waived_by_id` are brought into line.
* **The no-double-booking invariant.** It lived only in Python:
  `_assert_room_free` reads and then the insert writes, so two concurrent
  requests both saw the room free and both committed. PostgreSQL gets an
  exclusion constraint, which is the only thing that closes the race. The
  `'[)'` bound reproduces exactly the strict-comparison semantics the
  application already implements, so same-day turnover stays legal.
* **Invoice numbering.** `invoice_counters` replaces `SELECT COUNT(*) + 1`,
  which reused a number as soon as an invoice was deleted and collided under
  concurrency. Seeded from the highest number already issued per year so
  existing records keep their identity and nothing is handed out twice.
* **Indexes and one uniqueness rule.** `payments.paid_at` is range-filtered by
  every revenue query and had no index. The overlap check filters room, status
  and both dates together and had only single-column indexes. And a receipt
  number may now appear only once per reservation, which is what stops a double
  submit recording the guest's money twice.

SQLite cannot express the exclusion constraint, so that step is skipped there
and the application-level check stands alone — which is why the regression test
for the race is marked as PostgreSQL-only.

Revision ID: c58d31ea7f04
Revises: a1c4f7b920d3
Create Date: 2026-08-19 16:40:02.118374
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c58d31ea7f04"
down_revision: str | None = "a1c4f7b920d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BLOCKING = "('pending','confirmed','checked_in')"


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


# SQLite cannot alter a foreign key in place, so batch mode rewrites the table —
# and to rewrite it, it has to be told the shape to rewrite it into. These are
# frozen snapshots of the two tables as of this revision, with the corrected
# `ondelete` clauses. Deliberately literal and not imported from `app.models`: a
# migration that reads the current models stops describing a point in history the
# moment the models move on.
def _payments_table() -> sa.Table:
    return sa.Table(
        "payments",
        sa.MetaData(),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("reservation_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("method", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reference", sa.String(80), nullable=True),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_payment_id", sa.Integer(), nullable=True),
        sa.Column("recorded_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("amount > 0", name="ck_payment_amount"),
        sa.ForeignKeyConstraint(
            ["reservation_id"], ["reservations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["refunded_payment_id"], ["payments.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["recorded_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "reservation_id", "reference", name="uq_payment_reservation_reference"
        ),
        sa.Index("ix_payments_reservation_id", "reservation_id"),
        sa.Index("ix_payments_refunded_payment_id", "refunded_payment_id"),
        sa.Index("ix_payments_paid_at", "paid_at"),
    )


def _reservations_table() -> sa.Table:
    return sa.Table(
        "reservations",
        sa.MetaData(),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("reference", sa.String(20), nullable=False),
        sa.Column("guest_id", sa.Integer(), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("check_in_date", sa.Date(), nullable=False),
        sa.Column("check_out_date", sa.Date(), nullable=False),
        sa.Column("adults", sa.Integer(), nullable=False),
        sa.Column("children", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("nightly_rate", sa.Numeric(10, 2), nullable=False),
        sa.Column("total_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("special_requests", sa.Text(), nullable=True),
        sa.Column("actual_check_in", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_check_out", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.String(255), nullable=True),
        sa.Column("waived_amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("waived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("waived_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "check_out_date > check_in_date", name="ck_reservation_dates"
        ),
        sa.CheckConstraint("adults >= 1", name="ck_reservation_adults"),
        sa.ForeignKeyConstraint(["guest_id"], ["guests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["waived_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.Index("ix_reservations_reference", "reference", unique=True),
        sa.Index("ix_reservations_guest_id", "guest_id"),
        sa.Index("ix_reservations_room_id", "room_id"),
        sa.Index("ix_reservations_status", "status"),
        sa.Index("ix_reservations_check_in_date", "check_in_date"),
        sa.Index("ix_reservations_check_out_date", "check_out_date"),
        sa.Index(
            "ix_reservation_room_stay",
            "room_id",
            "status",
            "check_in_date",
            "check_out_date",
        ),
    )


def upgrade() -> None:
    # --- invoice number sequence -------------------------------------------
    op.create_table(
        "invoice_counters",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("last_number", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )
    # `unique=True` on the model's column produces a unique *index*, not a table
    # constraint, so the index alone is what keeps this in step with the models.
    op.create_index(
        "ix_invoice_counters_year", "invoice_counters", ["year"], unique=True
    )

    # Carry the existing numbering forward, so the first invoice issued after
    # this migration continues the series rather than restarting it.
    op.execute(
        """
        INSERT INTO invoice_counters (year, last_number)
        SELECT CAST(substr(invoice_number, 5, 4) AS INTEGER) AS yr,
               MAX(CAST(substr(invoice_number, 10) AS INTEGER))
        FROM invoices
        WHERE invoice_number LIKE 'INV-____-%'
        GROUP BY yr
        """
        if _is_sqlite()
        else """
        INSERT INTO invoice_counters (year, last_number)
        SELECT CAST(substring(invoice_number FROM 5 FOR 4) AS INTEGER) AS yr,
               MAX(CAST(substring(invoice_number FROM 10) AS INTEGER))
        FROM invoices
        WHERE invoice_number LIKE 'INV-____-%'
        GROUP BY yr
        """
    )

    # --- one receipt number per reservation ---------------------------------
    # Any duplicate already in the data has to go before the constraint can be
    # created. Keep the earliest row of each group and null the reference on the
    # rest rather than delete them: they are real movements of money, and only
    # the reference is in question.
    op.execute(
        """
        UPDATE payments SET reference = NULL
        WHERE reference IS NOT NULL
          AND id NOT IN (
            SELECT MIN(id) FROM payments
            WHERE reference IS NOT NULL
            GROUP BY reservation_id, reference
          )
        """
    )

    # --- schema drift, the new indexes and the uniqueness rule ---------------
    if _is_sqlite():
        # SQLite has no ALTER for a foreign key, so batch mode rewrites each
        # table from the snapshot above — which is why that snapshot carries the
        # indexes and the unique constraint as well: a rebuild produces exactly
        # what it is given, so anything omitted is silently dropped.
        #
        # This has to run on SQLite too, not only on PostgreSQL. Fixing it in one
        # engine and not the other is how the two environments came to differ in
        # the first place, and `alembic check` in CI now watches both.
        #
        # `recreate="always"`: with no other operation inside the block Alembic
        # sees no reason to rebuild, and the corrected foreign keys never land.
        with op.batch_alter_table(
            "payments", copy_from=_payments_table(), recreate="always"
        ):
            pass
        with op.batch_alter_table(
            "reservations", copy_from=_reservations_table(), recreate="always"
        ):
            pass
    else:
        op.create_index("ix_payments_paid_at", "payments", ["paid_at"])
        op.create_index(
            "ix_reservation_room_stay",
            "reservations",
            ["room_id", "status", "check_in_date", "check_out_date"],
        )
        op.create_unique_constraint(
            "uq_payment_reservation_reference",
            "payments",
            ["reservation_id", "reference"],
        )
        op.drop_constraint(
            "payments_recorded_by_id_fkey", "payments", type_="foreignkey"
        )
        op.drop_constraint(
            "payments_refunded_payment_id_fkey", "payments", type_="foreignkey"
        )
        op.drop_constraint(
            "reservations_waived_by_id_fkey", "reservations", type_="foreignkey"
        )
        op.create_foreign_key(
            "fk_payments_recorded_by_id_users",
            "payments",
            "users",
            ["recorded_by_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_foreign_key(
            "fk_payments_refunded_payment_id_payments",
            "payments",
            "payments",
            ["refunded_payment_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_foreign_key(
            "fk_reservations_waived_by_id_users",
            "reservations",
            "users",
            ["waived_by_id"],
            ["id"],
            ondelete="SET NULL",
        )

        # --- the invariant itself -------------------------------------------
        op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
        op.execute(
            f"""
            ALTER TABLE reservations ADD CONSTRAINT no_double_booking
              EXCLUDE USING gist (
                room_id WITH =,
                daterange(check_in_date, check_out_date, '[)') WITH &&
              ) WHERE (status IN {BLOCKING})
            """
        )


def downgrade() -> None:
    if not _is_sqlite():
        op.execute("ALTER TABLE reservations DROP CONSTRAINT IF EXISTS no_double_booking")
        for name, table in (
            ("fk_payments_recorded_by_id_users", "payments"),
            ("fk_payments_refunded_payment_id_payments", "payments"),
            ("fk_reservations_waived_by_id_users", "reservations"),
        ):
            op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(
            "payments_recorded_by_id_fkey", "payments", "users", ["recorded_by_id"], ["id"]
        )
        op.create_foreign_key(
            "payments_refunded_payment_id_fkey",
            "payments",
            "payments",
            ["refunded_payment_id"],
            ["id"],
        )
        op.create_foreign_key(
            "reservations_waived_by_id_fkey",
            "reservations",
            "users",
            ["waived_by_id"],
            ["id"],
        )

        op.drop_constraint(
            "uq_payment_reservation_reference", "payments", type_="unique"
        )
        op.drop_index("ix_reservation_room_stay", table_name="reservations")
        op.drop_index("ix_payments_paid_at", table_name="payments")

    op.drop_index("ix_invoice_counters_year", table_name="invoice_counters")
    op.drop_table("invoice_counters")
