"""Move amount time entries to expense reports

Revision ID: 5e5dbf0870c9
Revises: ec972f2ca14b
Create Date: 2026-09-18 00:04:25.648627+00:00

Data migration: every ``time_entries`` row with ``unit = 'amount'`` becomes an
``expense_reports`` row (one per distinct (user, project, calendar month)) with one
``expense_report_lines`` row per entry, then the original rows are deleted and a check
constraint (``unit <> 'amount'``) closes the door on new ones — expenses are claimed
through the expenses module's reports now, not the timesheet grid (see
``timesheets/CLAUDE.md`` and ``expenses/CLAUDE.md``).

A month a project already had sent to billing (a matching ``project_billing_periods`` row)
becomes an ``approved`` report with ``locked_at`` set to that period's ``sent_at``, matching
what the expenses module's own lock does today; every other month becomes a ``draft`` report,
since the old grid had no submit/approve workflow for these cells to preserve.

Pure SQL only — migrations must not import application code (see
``20260914_1150_36657462fe83_create_project_billing_items_table.py`` for the same rule
applied to ``DEFAULT_BILLING_ITEMS``).
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5e5dbf0870c9"
down_revision: str | Sequence[str] | None = "ec972f2ca14b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# `op.f(...)` marks this as the final, already-convention-formatted name — without it, the
# session's naming convention (`ck_%(table_name)s_%(constraint_name)s`, from `db/base.py`) would
# wrap it a second time into `ck_time_entries_ck_time_entries_unit_not_amount`. Computed lazily
# inside upgrade()/downgrade() rather than at module level: `op.f` needs an active Alembic
# `Operations` context, which only exists while a migration is actually running — importing this
# module merely to walk the revision graph (as `system.GetSystemStatus` does) doesn't have one.
def _check_constraint_name() -> str:
    return op.f("ck_time_entries_unit_not_amount")


def upgrade() -> None:
    op.execute(
        """
        WITH months AS (
            SELECT DISTINCT
                te.user_id,
                te.project_id,
                date_trunc('month', te.entry_date)::date AS period_start,
                (date_trunc('month', te.entry_date) + interval '1 month - 1 day')::date
                    AS period_end
            FROM time_entries te
            WHERE te.unit = 'amount'
        )
        INSERT INTO expense_reports (
            id, user_id, project_id, period_start, period_end, status,
            submitted_at, reviewed_at, reviewed_by_id, return_comment, locked_at,
            created_at, updated_at
        )
        SELECT
            gen_random_uuid(),
            m.user_id,
            m.project_id,
            m.period_start,
            m.period_end,
            (CASE WHEN pbp.sent_at IS NOT NULL THEN 'approved' ELSE 'draft' END)
                ::expense_report_status,
            NULL, NULL, NULL, NULL,
            pbp.sent_at,
            now(), now()
        FROM months m
        LEFT JOIN project_billing_periods pbp
            ON pbp.project_id = m.project_id AND pbp.period_start = m.period_start
        """
    )
    op.execute(
        """
        INSERT INTO expense_report_lines (
            id, report_id, billing_item_id, expense_date, amount, description, vendor,
            document_no, position, created_at, updated_at
        )
        SELECT
            gen_random_uuid(),
            er.id,
            te.billing_item_id,
            te.entry_date,
            te.quantity,
            COALESCE(NULLIF(te.note, ''), pbi.name),
            NULL,
            NULL,
            ROW_NUMBER() OVER (PARTITION BY er.id ORDER BY te.entry_date, te.id),
            now(), now()
        FROM time_entries te
        JOIN expense_reports er
            ON er.user_id = te.user_id
            AND er.project_id = te.project_id
            AND er.period_start = date_trunc('month', te.entry_date)::date
        JOIN project_billing_items pbi ON pbi.id = te.billing_item_id
        WHERE te.unit = 'amount'
        """
    )
    op.execute("DELETE FROM time_entries WHERE unit = 'amount'")
    op.create_check_constraint(_check_constraint_name(), "time_entries", "unit <> 'amount'")


def downgrade() -> None:
    op.drop_constraint(_check_constraint_name(), "time_entries", type_="check")
    # Best-effort mirror of upgrade(), moving every expense report line back to a time entry.
    # Only correct as an immediate round trip: an expense report created (or edited) by the
    # expenses module *after* this migration ran — normal use, once deployed — has no
    # equivalent in the old grid and gets folded back in anyway, which is why this is a manual
    # verification step (see the plan's Verification section), not a supported production
    # rollback path once real usage exists.
    op.execute(
        """
        INSERT INTO time_entries (
            id, user_id, project_id, billing_item_id, entry_date, quantity, unit, note,
            created_at, updated_at
        )
        SELECT
            gen_random_uuid(),
            er.user_id,
            er.project_id,
            erl.billing_item_id,
            erl.expense_date,
            erl.amount,
            'amount'::billing_unit,
            erl.description,
            now(), now()
        FROM expense_report_lines erl
        JOIN expense_reports er ON er.id = erl.report_id
        """
    )
    op.execute("DELETE FROM expense_reports")
