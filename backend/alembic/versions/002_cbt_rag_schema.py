"""CBT RAG schema for OKOA AI (Phase 4.5)

Revision ID: 002_cbt_rag_schema
Revises: 001_initial_schema
Create Date: 2026-10-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002_cbt_rag_schema'
down_revision: Union[str, None] = '001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enable pgvector extension if PostgreSQL is the dialect
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        bind.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector;"))

    # 2. Create cbt_strategies table
    op.create_table(
        'cbt_strategies',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('category', sa.String(length=64), nullable=False),
        sa.Column('language', sa.String(length=10), nullable=False, default='sw'),
        sa.Column('title', sa.String(length=128), nullable=False),
        sa.Column('summary', sa.String(length=256), nullable=False),
        sa.Column('instructions', sa.Text(), nullable=False),
        sa.Column('keywords', sa.String(length=512), nullable=False, default=''),
        sa.Column('embedding_json', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_cbt_strategies_category', 'cbt_strategies', ['category'])
    op.create_index('ix_cbt_strategies_language', 'cbt_strategies', ['language'])


def downgrade() -> None:
    op.drop_table('cbt_strategies')
