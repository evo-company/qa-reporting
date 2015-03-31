"""Add User model

Revision ID: 585c2538c65
Revises: None
Create Date: 2015-03-30 20:24:01.600382

"""

revision = '585c2538c65'
down_revision = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        'user',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=128), nullable=True),
        sa.Column('password', sa.String(length=128), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'uix_user_email',
        'user',
        [sa.text('lower("user".email)')],
        unique=True,
    )


def downgrade():
    op.drop_table('user')
