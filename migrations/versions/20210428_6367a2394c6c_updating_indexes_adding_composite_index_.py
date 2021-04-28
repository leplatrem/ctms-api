"""Updating indexes; adding composite index on update_ts and email_id, removing single column index on update_ts

Revision ID: 6367a2394c6c
Revises: 832a2a588c88
Create Date: 2021-04-28 16:35:37.437320

"""
# pylint: disable=no-member invalid-name
# no-member is triggered by alembic.op, which has dynamically added functions
# invalid-name is triggered by migration file names with a date prefix
# invalid-name is triggered by top-level alembic constants like revision instead of REVISION

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "6367a2394c6c"  # pragma: allowlist secret
down_revision = "832a2a588c88"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index("ix_emails_update_timestamp", table_name="emails")
    op.create_index(
        "bulk_read_index", "emails", ["update_timestamp", "email_id"], unique=False
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index("bulk_read_index", table_name="emails")
    op.create_index(
        "ix_emails_update_timestamp", "emails", ["update_timestamp"], unique=False
    )
    # ### end Alembic commands ###
