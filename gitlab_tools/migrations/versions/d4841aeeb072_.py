"""empty message

Revision ID: d4841aeeb072
Revises: 20bcb4b2673c
Create Date: 2018-06-21 22:06:12.215774

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'd4841aeeb072'
down_revision = '20bcb4b2673c'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('celery_taskmeta',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('task_id', sa.String(length=155), nullable=True),
    sa.Column('status', sa.String(length=50), nullable=True),
    sa.Column('result', sa.PickleType(), nullable=True),
    sa.Column('date_done', sa.DateTime(), nullable=True),
    sa.Column('traceback', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('task_id'),
    sqlite_autoincrement=True
    )
    op.create_table('celery_tasksetmeta',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('taskset_id', sa.String(length=155), nullable=True),
    sa.Column('result', sa.PickleType(), nullable=True),
    sa.Column('date_done', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('taskset_id'),
    sqlite_autoincrement=True
    )
    op.add_column('task_result', sa.Column('celery_taskmeta_id', sa.Integer(), nullable=False))
    op.create_index(op.f('ix_task_result_celery_taskmeta_id'), 'task_result', ['celery_taskmeta_id'], unique=False)
    op.drop_constraint('task_result_task_id_key', 'task_result', type_='unique')
    op.create_foreign_key(None, 'task_result', 'celery_taskmeta', ['celery_taskmeta_id'], ['id'])
    op.drop_column('task_result', 'result')
    op.drop_column('task_result', 'status')
    op.drop_column('task_result', 'date_done')
    op.drop_column('task_result', 'task_id')
    op.drop_column('task_result', 'traceback')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('task_result', sa.Column('traceback', sa.TEXT(), autoincrement=False, nullable=True))
    op.add_column('task_result', sa.Column('task_id', sa.VARCHAR(length=155), autoincrement=False, nullable=True))
    op.add_column('task_result', sa.Column('date_done', postgresql.TIMESTAMP(), autoincrement=False, nullable=True))
    op.add_column('task_result', sa.Column('status', sa.VARCHAR(length=50), autoincrement=False, nullable=True))
    op.add_column('task_result', sa.Column('result', postgresql.BYTEA(), autoincrement=False, nullable=True))
    op.drop_constraint(None, 'task_result', type_='foreignkey')
    op.create_unique_constraint('task_result_task_id_key', 'task_result', ['task_id'])
    op.drop_index(op.f('ix_task_result_celery_taskmeta_id'), table_name='task_result')
    op.drop_column('task_result', 'celery_taskmeta_id')
    op.drop_table('celery_tasksetmeta')
    op.drop_table('celery_taskmeta')
    # ### end Alembic commands ###
