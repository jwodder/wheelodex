from   datetime                   import datetime, timezone
import sqlalchemy as S
from   sqlalchemy.ext.declarative import declarative_base
from   sqlalchemy.orm             import backref, relationship, sessionmaker
from   sqlalchemy_utils           import JSONType
from   .                          import __version__

Base = declarative_base()

class WheelDatabase:
    def __init__(self, dburl_params):
        self.engine = S.create_engine(S.engine.url.URL(**dburl_params))
        Base.metadata.create_all(self.engine)
        self.session = None

    def __enter__(self):
        assert self.session is None, \
            'WheelDatabase context manager is not reentrant'
        self.session = sessionmaker(bind=self.engine)()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            self.session.commit()
        else:
            self.session.rollback()
        self.session.close()
        self.session = None
        return False

    @property
    def serial(self):
        # Serial ID of the last seen PyPI event
        ps = self.session.query(PyPISerial).one_or_none()
        return ps and ps.serial

    @serial.setter
    def serial(self, value):
        ps = self.session.query(PyPISerial).one_or_none()
        if ps is None:
            self.session.add(PyPISerial(serial=value))
        else:
            ps.serial = max(ps.serial, value)

    def add_wheel(self, wheel, serial=None):
        whl = self.session.query(Wheel)\
                          .filter(Wheel.filename == wheel.filename)\
                          .one_or_none()
        if whl is None:
            self.session.add(wheel)
        else:
            whl.queued = wheel.queued
        if serial is not None:
            self.serial = serial

    def unqueue_wheel(self, whl):
        if isinstance(whl, Wheel):
            whl.queued = False
        else:
            self.session.query(Wheel)\
                        .filter(Wheel.filename == whl)\
                        .update({Wheel.queued: False})

    def iterqueue(self):
        ### Would leaving off the ".all()" give an iterable that plays well
        ### with unqueue_wheel()?
        return self.session.query(Wheel)\
                           .filter(Wheel.queued == True)\
                           .all()  # noqa: E712

    def add_wheel_data(self, wheel, raw_data):
        wheel.data = WheelData.from_raw_data(self.session, raw_data)

    def remove_wheel(self, filename, serial=None):
        self.session.query(Wheel)\
                    .filter(Wheel.filename == filename)\
                    .delete()
        if serial is not None:
            self.serial = serial

    def remove_version(self, project, version, serial=None):
        # Note that this filters by PyPI project & version, not by wheel
        # filename project & version, as this method is meant to be called in
        # response to "remove" events in the PyPI changelog.
        self.session.query(Wheel)\
                    .filter(Wheel.project == project)\
                    .filter(Wheel.version == version)\
                    .delete()
        if serial is not None:
            self.serial = serial

    def remove_project(self, project, serial=None):
        # Note that this filters by PyPI project, not by wheel filename
        # project, as this method is meant to be called in response to "remove"
        # events in the PyPI changelog.
        self.session.query(Wheel).filter(Wheel.project == project).delete()
        if serial is not None:
            self.serial = serial

    def add_wheel_error(self, wheel, errmsg):
        wheel.errors.append(ProcessingError(
            errmsg            = errmsg,
            timestamp         = datetime.now(timezone.utc),
            wheelodex_version = __version__,
        ))


class PyPISerial(Base):
    __tablename__ = 'pypi_serial'

    id     = S.Column(S.Integer, primary_key=True, nullable=False)  # noqa: B001
    serial = S.Column(S.Integer, nullable=False)


class Wheel(Base):
    """
    A table of *all* wheels available on PyPI, even ones we're not storing data
    for.  We store all the wheels so that, if we ever decide to go back and
    analyze wheels we declined to analyze earlier, we don't have to spend hours
    scraping the entire XML-RPC API to find them.  Also, the table provides
    statistics on wheels that can be useful for deciding whether to go back and
    analyze more wheels in the first place.
    """

    __tablename__ = 'wheels'

    id = S.Column(S.Integer, primary_key=True, nullable=False)  # noqa: B001
    filename = S.Column(S.Unicode(2048), nullable=False, unique=True)
    url      = S.Column(S.Unicode(2048), nullable=False)
    project  = S.Column(S.Unicode(2048), nullable=False)
    version  = S.Column(S.Unicode(2048), nullable=False)
    size     = S.Column(S.Integer, nullable=False)
    md5      = S.Column(S.Unicode(32), nullable=True)
    sha256   = S.Column(S.Unicode(64), nullable=True)
    uploaded = S.Column(S.Unicode(32), nullable=False)
    queued   = S.Column(S.Boolean, nullable=False)


class ProcessingError(Base):
    __tablename__ = 'processing_errors'

    id = S.Column(S.Integer, primary_key=True, nullable=False)  # noqa: B001
    wheel_id  = S.Column(S.Integer, S.ForeignKey('wheels.id'), nullable=False)
    wheel     = relationship('Wheel', backref='errors')
    errmsg    = S.Column(S.Unicode(65535), nullable=False)
    timestamp = S.Column(S.DateTime(timezone=True), nullable=False)
    wheelodex_version = S.Column(S.Unicode(32), nullable=False)


class WheelData(Base):
    __tablename__ = 'wheel_data'

    id = S.Column(S.Integer, primary_key=True, nullable=False)  # noqa: B001
    wheel_id  = S.Column(S.Integer, S.ForeignKey('wheels.id'), nullable=False,
                         unique=True)
    wheel     = relationship('Wheel', backref=backref('data', uselist=False))
    raw_data  = S.Column(JSONType, nullable=False)
    #: The project name as extracted from the wheel filename.  This may differ
    #: from the project name as reported on PyPI, even after normalization.
    project   = S.Column(S.Unicode(2048), nullable=False)
    version   = S.Column(S.Unicode(2048), nullable=False)
    #: The time at which the raw data was extracted from the wheel and added to
    #: the database
    processed = S.Column(S.DateTime(timezone=True), nullable=False)
    #: The version of `wheelodex` under which the WheelData's columns and
    #: relations were filled in
    wheelodex_version = S.Column(S.Unicode(32), nullable=False)

    @classmethod
    def from_raw_data(cls, session, raw_data):
        return cls(
            raw_data  = raw_data,
            processed = datetime.now(timezone.utc),
            **cls.parse_raw_data(session, raw_data),
        )

    @staticmethod
    def parse_raw_data(session, raw_data):
        return {
            "wheelodex_version": __version__,
            "project": raw_data["project"],
            "version": raw_data["version"],
            "entry_points": [
                EntryPoint(
                    group=EntryPointGroup.from_name(session, group),
                    name=e,
                )
                for group, eps in raw_data["dist_info"].get("entry_points", {})
                                                       .items()
                for e in eps
            ],
        }

    def update_structure(self, session):
        """
        Update the `WheelData` and its subobjects for the current database
        schema
        """
        ### TODO: For subobjects like EntryPoints, try to eliminate replacing
        ### unchanged subobjects with equal subobjects with new IDs every time
        ### this method is called
        for k,v in self.parse_raw_data(session, self.raw_data):
            setattr(self, k, v)


class EntryPointGroup(Base):
    __tablename__ = 'entry_point_groups'

    id = S.Column(S.Integer, primary_key=True, nullable=False)  # noqa: B001
    name        = S.Column(S.Unicode(2048), nullable=False, unique=True)
    description = S.Column(S.Unicode(65535), nullable=True, default=None)

    @classmethod
    def from_name(cls, session, name):
        epg = session.query(cls).filter(cls.name == name).one_or_none()
        if epg is None:
            epg = cls(name=name)
            session.add(epg)
        return epg


class EntryPoint(Base):
    __tablename__ = 'entry_points'

    id = S.Column(S.Integer, primary_key=True, nullable=False)  # noqa: B001
    wheel_data_id = S.Column(S.Integer, S.ForeignKey('wheel_data.id'),
                             nullable=False)
    wheel_data    = relationship('WheelData', backref=backref('entry_points'))
    group_id      = S.Column(S.Integer, S.ForeignKey('entry_point_groups.id'),
                             nullable=False)
    group         = relationship('EntryPointGroup')
    name          = S.Column(S.Unicode(2048), nullable=False)
