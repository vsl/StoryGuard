"""Retain each model attempt without inventing a decision for technical failures."""

from alembic import op
import sqlalchemy as sa

revision = "20260830_11"
down_revision = "20260830_10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    table = "entity_resolution_decisions"
    op.add_column(table, sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"))
    op.alter_column(table, "decision", existing_type=sa.String(16), nullable=True)
    op.drop_constraint("entity_resolution_decisions_candidate_id_source_key", table, type_="unique")
    op.create_unique_constraint("uq_resolution_decision_attempt", table, ["candidate_id", "source", "attempt"])
    op.create_check_constraint("ck_resolution_decision_attempt", table, "attempt >= 1 AND (source = 'model' OR attempt = 1)")


def downgrade() -> None:
    # Fail rather than delete retry history or fabricate decisions to fit the old schema.
    table = "entity_resolution_decisions"
    op.create_unique_constraint("entity_resolution_decisions_candidate_id_source_key", table, ["candidate_id", "source"])
    op.alter_column(table, "decision", existing_type=sa.String(16), nullable=False)
    op.drop_constraint("ck_resolution_decision_attempt", table, type_="check")
    op.drop_constraint("uq_resolution_decision_attempt", table, type_="unique")
    op.drop_column(table, "attempt")
