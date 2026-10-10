"""users: 42 identity instead of username and password

Revision ID: 5cf192bbe0a6
Revises: b7b043dad90b
Create Date: 2026-10-10 11:53:00.647289
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5cf192bbe0a6"
down_revision: str | None = "b7b043dad90b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Users were username/password accounts and none are real (D16). A 42
    # identity cannot be made up for them, so they go; their refresh tokens
    # are deleted with them (ON DELETE CASCADE).
    op.execute("DELETE FROM users")
    op.add_column("users", sa.Column("intra_id", sa.Integer(), nullable=False))
    op.add_column("users", sa.Column("login", sa.String(), nullable=False))
    op.add_column("users", sa.Column("campus_id", sa.Integer(), nullable=False))
    op.add_column("users", sa.Column("campus_name", sa.String(), nullable=False))
    op.drop_constraint(op.f("users_username_key"), "users", type_="unique")
    op.create_unique_constraint("users_intra_id_key", "users", ["intra_id"])
    op.create_unique_constraint("users_login_key", "users", ["login"])

    op.drop_column("users", "password_hash")
    op.drop_column("users", "username")


def downgrade() -> None:
    # The old columns are NOT NULL and there is no username/password for a
    # 42 user, so the rows cannot be kept either way.
    op.execute("DELETE FROM users")
    op.add_column("users", sa.Column("username", sa.VARCHAR(), autoincrement=False, nullable=False))
    op.add_column(
        "users", sa.Column("password_hash", sa.VARCHAR(), autoincrement=False, nullable=False)
    )
    op.drop_constraint("users_login_key", "users", type_="unique")
    op.drop_constraint("users_intra_id_key", "users", type_="unique")
    op.create_unique_constraint(
        op.f("users_username_key"), "users", ["username"], postgresql_nulls_not_distinct=False
    )
    op.drop_column("users", "campus_name")
    op.drop_column("users", "campus_id")
    op.drop_column("users", "login")
    op.drop_column("users", "intra_id")
