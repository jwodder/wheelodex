"""Move summary

Revision ID: f43499b4f914
Revises: 8820a6b34f40
Create Date: 2018-10-14 16:23:22.552013+00:00

"""
from   alembic import op
import sqlalchemy as S
from   sqlalchemy_utils import JSONType

# revision identifiers, used by Alembic.
revision = 'f43499b4f914'
down_revision = '8820a6b34f40'
branch_labels = None
depends_on = None

schema = S.MetaData()

project = S.Table(
    'projects', schema,
    S.Column('id', S.Integer, primary_key=True, nullable=False),
    S.Column('name', S.Unicode(2048), nullable=False, unique=True),
    S.Column('display_name', S.Unicode(2048), nullable=False, unique=True),
    S.Column('summary', S.Unicode(2048), nullable=True),
)

version = S.Table(
    'versions', schema,
    S.Column('id', S.Integer, primary_key=True, nullable=False),
    S.Column(
        'project_id',
        S.Integer,
        S.ForeignKey('projects.id', ondelete='CASCADE'),
        nullable=False,
    ),
    S.Column('name', S.Unicode(2048), nullable=False),
    S.Column('display_name', S.Unicode(2048), nullable=False),
    S.Column('ordering', S.Integer, nullable=False, default=0),
    S.UniqueConstraint('project_id', 'name'),
)

wheel = S.Table(
    'wheels', schema,
    S.Column('id', S.Integer, primary_key=True, nullable=False),
    S.Column('filename', S.Unicode(2048), nullable=False, unique=True),
    S.Column('url', S.Unicode(2048), nullable=False),
    S.Column(
        'version_id',
        S.Integer,
        S.ForeignKey('versions.id', ondelete='CASCADE'),
        nullable=False,
    ),
    S.Column('size', S.Integer, nullable=False),
    S.Column('md5', S.Unicode(32), nullable=True),
    S.Column('sha256', S.Unicode(64), nullable=True),
    S.Column('uploaded', S.Unicode(32), nullable=False),
    S.Column('ordering', S.Integer, nullable=False, default=0),
)

wheel_data = S.Table(
    'wheel_data', schema,
    S.Column('id', S.Integer, primary_key=True, nullable=False),
    S.Column(
        'wheel_id',
        S.Integer,
        S.ForeignKey('wheels.id', ondelete='CASCADE'),
        nullable=False,
        unique=True,
    ),
    S.Column('raw_data', JSONType, nullable=False),
    S.Column('processed', S.DateTime(timezone=True), nullable=False),
    S.Column('wheel_inspect_version', S.Unicode(32), nullable=False),
    S.Column('summary', S.Unicode(2048), nullable=True),
    S.Column('valid', S.Boolean, nullable=False),
)

def upgrade():
    op.add_column('projects', S.Column('summary', S.Unicode(length=2048), nullable=True))
    conn = op.get_bind()
    subq = S.select([
        project.c.id,
        wheel_data.c.summary,
        S.func.ROW_NUMBER().over(
            partition_by=project.c.id,
            order_by=(version.c.ordering.desc(), wheel.c.ordering.desc()),
        ).label('rownum'),
    ]).select_from(project.join(version).join(wheel).join(wheel_data))\
      .order_by(project.c.name.asc())\
      .cte()
    for pid, summary in conn.execute(S.select([
        subq.c.id, subq.c.summary
    ]).where(subq.c.rownum == 1)):
        conn.execute(
            project.update().values(summary=summary).where(project.c.id == pid)
        )
    op.drop_column('wheel_data', 'summary')

def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('wheel_data', S.Column('summary', S.VARCHAR(length=2048), autoincrement=False, nullable=True))
    op.drop_column('projects', 'summary')
    # ### end Alembic commands ###
