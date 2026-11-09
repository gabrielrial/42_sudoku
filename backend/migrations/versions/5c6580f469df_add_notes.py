"""add notes to game_sessions and game_moves

Revision ID: 5c6580f469df
Revises: d33545f4b925
Create Date: 2026-11-09 12:00:00.000000

Written by hand: autogenerate does not see changes to CHECK constraints.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5c6580f469df"
down_revision: str | None = "d33545f4b925"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOTES_CHECK = (
    "cardinality(notes) = 81 AND array_position(notes, NULL) IS NULL "
    "AND 0 <= ALL (notes) AND 511 >= ALL (notes)"
)


def upgrade() -> None:
    op.add_column(
        "game_sessions",
        sa.Column(
            "notes",
            sa.ARRAY(sa.SmallInteger()),
            server_default=sa.text("array_fill(0, ARRAY[81])::smallint[]"),
            nullable=False,
        ),
    )
    op.create_check_constraint("game_sessions_notes_check", "game_sessions", NOTES_CHECK)
    # Every game now has notes, empty ones included: all of them are version 2.
    op.alter_column("game_sessions", "state_version", server_default=sa.text("2"))
    op.execute("UPDATE game_sessions SET state_version = 2")

    op.add_column("game_moves", sa.Column("previous_notes", sa.SmallInteger(), nullable=True))
    op.add_column("game_moves", sa.Column("notes", sa.SmallInteger(), nullable=True))
    op.drop_constraint("game_moves_kind_check", "game_moves", type_="check")
    op.create_check_constraint(
        "game_moves_kind_check", "game_moves", "kind IN ('input', 'notes', 'clear', 'check')"
    )
    op.create_check_constraint(
        "game_moves_notes_check",
        "game_moves",
        "(kind = 'notes') = "
        "(cell IS NOT NULL AND previous_notes IS NOT NULL AND notes IS NOT NULL)",
    )
    op.create_check_constraint(
        "game_moves_previous_notes_check", "game_moves", "previous_notes BETWEEN 0 AND 511"
    )
    op.create_check_constraint(
        "game_moves_notes_range_check", "game_moves", "notes BETWEEN 0 AND 511"
    )


def downgrade() -> None:
    # The notes moves have nowhere to go once the kind is gone.
    op.execute("DELETE FROM game_moves WHERE kind = 'notes'")
    op.drop_constraint("game_moves_notes_range_check", "game_moves", type_="check")
    op.drop_constraint("game_moves_previous_notes_check", "game_moves", type_="check")
    op.drop_constraint("game_moves_notes_check", "game_moves", type_="check")
    op.drop_constraint("game_moves_kind_check", "game_moves", type_="check")
    op.create_check_constraint(
        "game_moves_kind_check", "game_moves", "kind IN ('input', 'clear', 'check')"
    )
    op.drop_column("game_moves", "notes")
    op.drop_column("game_moves", "previous_notes")

    op.execute("UPDATE game_sessions SET state_version = 1")
    op.alter_column("game_sessions", "state_version", server_default=sa.text("1"))
    op.drop_constraint("game_sessions_notes_check", "game_sessions", type_="check")
    op.drop_column("game_sessions", "notes")
