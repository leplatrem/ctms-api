"""Adding index for stripe_invoice_line_item.stripe_invoice_id and stripe_invoice_line_item.stripe_price_id

Revision ID: 406251207612
Revises: 6c7724982996
Create Date: 2022-11-09 20:24:42.452313

"""
# pylint: disable=no-member invalid-name
# no-member is triggered by alembic.op, which has dynamically added functions
# invalid-name is triggered by migration file names with a date prefix
# invalid-name is triggered by top-level alembic constants like revision instead of REVISION

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = '406251207612'  # pragma: allowlist secret
down_revision = '6c7724982996'  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_index(op.f('ix_stripe_invoice_line_item_stripe_invoice_id'), 'stripe_invoice_line_item', ['stripe_invoice_id'], unique=False)
    op.create_index(op.f('ix_stripe_invoice_line_item_stripe_price_id'), 'stripe_invoice_line_item', ['stripe_price_id'], unique=False)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_stripe_invoice_line_item_stripe_price_id'), table_name='stripe_invoice_line_item')
    op.drop_index(op.f('ix_stripe_invoice_line_item_stripe_invoice_id'), table_name='stripe_invoice_line_item')
    # ### end Alembic commands ###
