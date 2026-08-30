"""Persist the extractor selected at upload on each manuscript version."""

import sqlalchemy as sa
from alembic import op

revision = "20260830_08"
down_revision = "20260830_07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "manuscript_versions",
        sa.Column("extraction_model", sa.String(64), nullable=False, server_default="gemma4-e4b"),
    )
    op.create_check_constraint(
        "ck_manuscript_extraction_model",
        "manuscript_versions",
        "extraction_model IN ('gemma4-e4b', 'gliner2.5-base-v1', 'qwen3.5-9b')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_manuscript_extraction_model", "manuscript_versions", type_="check")
    op.drop_column("manuscript_versions", "extraction_model")
