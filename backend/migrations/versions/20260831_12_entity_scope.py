"""Six supported entity categories; incompatible test data must be reset explicitly."""

from alembic import op

revision = "20260831_12"
down_revision = "20260830_11"
branch_labels = None
depends_on = None


def _types(values: str) -> None:
    for table, name in (("entities", "ck_entity_type"), ("entity_mentions", "ck_entity_mention_type")):
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, f"entity_type IN ({values})")


def upgrade() -> None:
    # Never silently delete rows in a migration. This iteration explicitly uses a fresh test DB.
    _types("'character','facility','gpe','location','organization','vehicle'")


def downgrade() -> None:
    _types("'character','location','object','organization','other'")
