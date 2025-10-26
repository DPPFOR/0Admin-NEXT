"""inbox_parsed_items_and_chunks_with_views

Revision ID: beff93c8d43a
Revises: 20250216_flags_and_mvr_preview
Create Date: 2025-10-24 16:06:30.891455+00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'beff93c8d43a'
down_revision = '20250216_flags_and_mvr_preview'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create inbox_parsed schema if it doesn't exist
    op.execute("CREATE SCHEMA IF NOT EXISTS inbox_parsed")
    
    # Create ops schema if it doesn't exist
    op.execute("CREATE SCHEMA IF NOT EXISTS ops")
    
    # Check if parsed_items table already exists
    connection = op.get_bind()
    result = connection.execute(text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'inbox_parsed' 
            AND table_name = 'parsed_items'
        )
    """))
    
    if not result.scalar():
        # Create parsed_items table
        op.create_table(
            'parsed_items',
            sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True),
            sa.Column('tenant_id', postgresql.UUID(as_uuid=False), nullable=False),
            sa.Column('content_hash', sa.String(), nullable=False),
            sa.Column('doc_type', sa.String(), nullable=False),
            sa.Column('doctype', sa.String(), nullable=False, server_default=sa.text("'unknown'")),
            sa.Column('amount', sa.Numeric(18, 4)),
            sa.Column('invoice_no', sa.String()),
            sa.Column('due_date', sa.Date()),
            sa.Column('quality_status', sa.String(), nullable=False, server_default=sa.text("'needs_review'")),
            sa.Column('confidence', sa.Numeric(5, 2), nullable=False, server_default=sa.text("0")),
            sa.Column('rules', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column('flags', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column('mvr_preview', sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column('mvr_score', sa.Numeric(5, 2)),
            sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())")),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())")),
            schema='inbox_parsed'
        )
        
        # Create unique constraint on parsed_items
        op.create_unique_constraint(
            'uq_parsed_items_tenant_content_hash',
            'parsed_items',
            ['tenant_id', 'content_hash'],
            schema='inbox_parsed'
        )
        
        # Create indexes for parsed_items
        op.create_index('ix_parsed_items_tenant_id', 'parsed_items', ['tenant_id'], schema='inbox_parsed')
        op.create_index('ix_parsed_items_created_at', 'parsed_items', ['created_at'], schema='inbox_parsed')
        op.create_index('ix_parsed_items_doctype', 'parsed_items', ['doctype'], schema='inbox_parsed')
        op.create_index('ix_parsed_items_quality_status', 'parsed_items', ['quality_status'], schema='inbox_parsed')
    
    # Check if parsed_item_chunks table already exists
    result = connection.execute(text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'inbox_parsed' 
            AND table_name = 'parsed_item_chunks'
        )
    """))
    
    if not result.scalar():
        # Create parsed_item_chunks table
        op.create_table(
            'parsed_item_chunks',
            sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True),
            sa.Column('parsed_item_id', postgresql.UUID(as_uuid=False), nullable=False),
            sa.Column('seq', sa.Integer(), nullable=False),
            sa.Column('kind', sa.String(), nullable=False),
            sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())")),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())")),
            schema='inbox_parsed'
        )
        
        # Create unique constraint on parsed_item_chunks
        op.create_unique_constraint(
            'uq_parsed_item_chunks_item_kind_seq',
            'parsed_item_chunks',
            ['parsed_item_id', 'kind', 'seq'],
            schema='inbox_parsed'
        )
        
        # Create foreign key constraint
        op.create_foreign_key(
            'fk_parsed_item_chunks_parsed_item_id_parsed_items_id',
            'parsed_item_chunks',
            'parsed_items',
            ['parsed_item_id'],
            ['id'],
            ondelete='CASCADE',
            schema='inbox_parsed'
        )
        
        # Create index for parsed_item_chunks
        op.create_index('ix_parsed_item_chunks_parsed_item_id', 'parsed_item_chunks', ['parsed_item_id'], schema='inbox_parsed')
    
    # Create updated_at trigger function
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = timezone('utc', now());
            RETURN NEW;
        END;
        $$ language 'plpgsql';
    """)
    
    # Create triggers for updated_at (only if they don't exist)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_parsed_items_updated_at') THEN
                CREATE TRIGGER update_parsed_items_updated_at 
                BEFORE UPDATE ON inbox_parsed.parsed_items 
                FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
            END IF;
        END $$;
    """)
    
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_parsed_item_chunks_updated_at') THEN
                CREATE TRIGGER update_parsed_item_chunks_updated_at 
                BEFORE UPDATE ON inbox_parsed.parsed_item_chunks 
                FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
            END IF;
        END $$;
    """)
    
    # Drop existing views first
    op.execute("DROP VIEW IF EXISTS inbox_parsed.v_inbox_by_tenant CASCADE")
    op.execute("DROP VIEW IF EXISTS inbox_parsed.v_invoices_latest CASCADE")
    
    # Create views
    op.execute("""
        CREATE VIEW inbox_parsed.v_inbox_by_tenant AS
        SELECT 
            tenant_id,
            COUNT(*) as total_items,
            COUNT(CASE WHEN doctype = 'invoice' THEN 1 END) as invoices,
            COUNT(CASE WHEN doctype = 'payment' THEN 1 END) as payments,
            COUNT(CASE WHEN doctype = 'other' THEN 1 END) as others,
            AVG(confidence) as avg_confidence
        FROM inbox_parsed.parsed_items
        GROUP BY tenant_id;
    """)
    
    op.execute("""
        CREATE VIEW inbox_parsed.v_invoices_latest AS
        SELECT * FROM inbox_parsed.parsed_items 
        WHERE doctype = 'invoice'
        ORDER BY created_at DESC;
    """)
    
    # Check if audit_log table already exists
    result = connection.execute(text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'ops' 
            AND table_name = 'audit_log'
        )
    """))
    
    if not result.scalar():
        # Create audit_log table
        op.create_table(
            'audit_log',
            sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True),
            sa.Column('ts', sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())")),
            sa.Column('trace_id', sa.String()),
            sa.Column('actor', sa.String()),
            sa.Column('tenant_id', postgresql.UUID(as_uuid=False)),
            sa.Column('item_id', postgresql.UUID(as_uuid=False)),
            sa.Column('source', sa.String()),
            sa.Column('op', sa.String()),
            sa.Column('meta', postgresql.JSONB(astext_type=sa.Text())),
            schema='ops'
        )


def downgrade() -> None:
    # Drop views
    op.execute("DROP VIEW IF EXISTS inbox_parsed.v_invoices_latest")
    op.execute("DROP VIEW IF EXISTS inbox_parsed.v_inbox_by_tenant")
    
    # Drop triggers
    op.execute("DROP TRIGGER IF EXISTS update_parsed_item_chunks_updated_at ON inbox_parsed.parsed_item_chunks")
    op.execute("DROP TRIGGER IF EXISTS update_parsed_items_updated_at ON inbox_parsed.parsed_items")
    
    # Drop function
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column()")
    
    # Drop tables
    op.drop_table('audit_log', schema='ops')
    op.drop_table('parsed_item_chunks', schema='inbox_parsed')
    op.drop_table('parsed_items', schema='inbox_parsed')
    
    # Drop schema
    op.execute("DROP SCHEMA IF EXISTS inbox_parsed")
