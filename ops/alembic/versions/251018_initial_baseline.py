"""Initial baseline

Revision ID: 251018_initial_baseline
Revises: 000000000000
Create Date: 2025-10-18 17:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "251018_initial_baseline"
down_revision = "000000000000"
branch_labels = None
depends_on = None

def upgrade() -> None:
    """Initial baseline - schema zero_admin, extension, trigger function"""

    # Create schema zero_admin (multi-tenant scope)
    op.execute("CREATE SCHEMA IF NOT EXISTS zero_admin")

    # Extension for encryption/crypto functions (if available)
    # Note: Requires SUPERUSER or appropriate rights
    try:
        op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    except Exception as e:
        # Log but continue if extension cannot be created
        op.execute("SELECT 'Note: pgcrypto extension creation failed - may require SUPERUSER rights'")

    # Trigger function for consistent updated_at timestamps (UTC)
    op.execute("""
        CREATE OR REPLACE FUNCTION zero_admin.set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = timezone('utc', now());
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    """Baseline downgrade - remove function only (preserve schema/extension)"""

    # Drop the trigger function
    op.execute("DROP FUNCTION IF EXISTS zero_admin.set_updated_at()")

    # Note: Schema and extension are NOT dropped to preserve infrastructure
    # Manual cleanup may be required if schema removal is desired
