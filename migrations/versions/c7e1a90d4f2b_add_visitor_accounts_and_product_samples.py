"""Add the visitor accounts, the samples of the products and the record
of who opened them.

The tables are new. Nothing that existed before is changed, so the
migration can be turned back without touching the catalogue.

Revision ID: c7e1a90d4f2b
Revises: a69c5352e3c7
Create Date: 2026-11-22

"""
from alembic import op
import sqlalchemy as sa

revision = 'c7e1a90d4f2b'
down_revision = 'a69c5352e3c7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'visitors',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=190), nullable=False),
        sa.Column('display_name', sa.String(length=120), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('organization', sa.String(length=160), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('last_login_at', sa.DateTime(), nullable=True),
        sa.Column('last_login_ip_hash', sa.String(length=64), nullable=True),
        sa.Column('login_count', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_visitors_email'), 'visitors', ['email'], unique=True)
    op.create_index(op.f('ix_visitors_created_at'), 'visitors', ['created_at'], unique=False)

    op.create_table(
        'portfolio_live_links',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('portfolio_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=True),
        sa.Column('title', sa.String(length=180), nullable=False),
        sa.Column('url', sa.String(length=1000), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('display_mode', sa.String(length=20), nullable=False),
        sa.Column('requires_login', sa.Boolean(), nullable=False),
        sa.Column('is_published', sa.Boolean(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('open_count', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['portfolio_id'], ['portfolios.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_portfolio_live_links_portfolio_id'), 'portfolio_live_links', ['portfolio_id'], unique=False)
    op.create_index(op.f('ix_portfolio_live_links_product_id'), 'portfolio_live_links', ['product_id'], unique=False)
    op.create_index(op.f('ix_portfolio_live_links_display_mode'), 'portfolio_live_links', ['display_mode'], unique=False)
    op.create_index(op.f('ix_portfolio_live_links_is_published'), 'portfolio_live_links', ['is_published'], unique=False)
    op.create_index(op.f('ix_portfolio_live_links_created_at'), 'portfolio_live_links', ['created_at'], unique=False)

    op.create_table(
        'sample_accesses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('visitor_id', sa.Integer(), nullable=False),
        sa.Column('live_link_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=True),
        sa.Column('opened_at', sa.DateTime(), nullable=True),
        sa.Column('ip_hash', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['visitor_id'], ['visitors.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['live_link_id'], ['portfolio_live_links.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_sample_accesses_visitor_id'), 'sample_accesses', ['visitor_id'], unique=False)
    op.create_index(op.f('ix_sample_accesses_live_link_id'), 'sample_accesses', ['live_link_id'], unique=False)
    op.create_index(op.f('ix_sample_accesses_product_id'), 'sample_accesses', ['product_id'], unique=False)
    op.create_index(op.f('ix_sample_accesses_created_at'), 'sample_accesses', ['created_at'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_sample_accesses_created_at'), table_name='sample_accesses')
    op.drop_index(op.f('ix_sample_accesses_product_id'), table_name='sample_accesses')
    op.drop_index(op.f('ix_sample_accesses_live_link_id'), table_name='sample_accesses')
    op.drop_index(op.f('ix_sample_accesses_visitor_id'), table_name='sample_accesses')
    op.drop_table('sample_accesses')

    op.drop_index(op.f('ix_portfolio_live_links_created_at'), table_name='portfolio_live_links')
    op.drop_index(op.f('ix_portfolio_live_links_is_published'), table_name='portfolio_live_links')
    op.drop_index(op.f('ix_portfolio_live_links_display_mode'), table_name='portfolio_live_links')
    op.drop_index(op.f('ix_portfolio_live_links_product_id'), table_name='portfolio_live_links')
    op.drop_index(op.f('ix_portfolio_live_links_portfolio_id'), table_name='portfolio_live_links')
    op.drop_table('portfolio_live_links')

    op.drop_index(op.f('ix_visitors_created_at'), table_name='visitors')
    op.drop_index(op.f('ix_visitors_email'), table_name='visitors')
    op.drop_table('visitors')
