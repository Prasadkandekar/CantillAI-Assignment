"""chat history

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-20 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('conversations',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('owner', sa.String(length=128), nullable=False),
    sa.Column('title', sa.String(length=120), nullable=False),
    sa.Column('session_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['session_id'], ['chat_sessions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('conversations', schema=None) as batch_op:
        batch_op.create_index('ix_conversations_owner_updated', ['owner', 'updated_at'], unique=False)
    op.create_table('conversation_messages',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('conversation_id', sa.Integer(), nullable=False),
    sa.Column('role', sa.String(length=16), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('payload', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('conversation_messages', schema=None) as batch_op:
        batch_op.create_index('ix_conv_messages_conv', ['conversation_id', 'id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('conversation_messages', schema=None) as batch_op:
        batch_op.drop_index('ix_conv_messages_conv')
    op.drop_table('conversation_messages')
    with op.batch_alter_table('conversations', schema=None) as batch_op:
        batch_op.drop_index('ix_conversations_owner_updated')
    op.drop_table('conversations')
