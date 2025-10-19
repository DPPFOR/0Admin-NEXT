"""Create zero_admin schema

Revision ID: 000000000000
Revises: None
Create Date: 2025-10-18 17:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "000000000000"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Create zero_admin schema first (before any other migrations)"""

    # Create schema zero_admin (tenant scope)
    op.execute("CREATE SCHEMA IF NOT EXISTS zero_admin")


def downgrade() -> None:
    """Drop zero_admin schema (dangerous - removes all contents)"""

    # Drop schema and all contents
    op.execute("DROP SCHEMA IF EXISTS zero_admin CASCADE")
