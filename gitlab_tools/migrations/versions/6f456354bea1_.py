"""empty message

Revision ID: 6f456354bea1
Revises: d4841aeeb072
Create Date: 2018-06-21 22:16:03.577289

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6f456354bea1'
down_revision = 'd4841aeeb072'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('task_result', sa.Column('taskmeta_id', sa.Integer(), nullable=False))
    op.create_index(op.f('ix_task_result_taskmeta_id'), 'task_result', ['taskmeta_id'], unique=True)
    op.drop_index('ix_task_result_celery_taskmeta_id', table_name='task_result')
    op.drop_constraint('task_result_celery_taskmeta_id_fkey', 'task_result', type_='foreignkey')
    op.create_foreign_key(None, 'task_result', 'celery_taskmeta', ['taskmeta_id'], ['id'])
    op.drop_column('task_result', 'celery_taskmeta_id')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('task_result', sa.Column('celery_taskmeta_id', sa.INTEGER(), autoincrement=False, nullable=False))
    op.drop_constraint(None, 'task_result', type_='foreignkey')
    op.create_foreign_key('task_result_celery_taskmeta_id_fkey', 'task_result', 'celery_taskmeta', ['celery_taskmeta_id'], ['id'])
    op.create_index('ix_task_result_celery_taskmeta_id', 'task_result', ['celery_taskmeta_id'], unique=False)
    op.drop_index(op.f('ix_task_result_taskmeta_id'), table_name='task_result')
    op.drop_column('task_result', 'taskmeta_id')
    # ### end Alembic commands ###
