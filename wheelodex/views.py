""" Flask views """

from   collections     import OrderedDict
from   functools       import wraps
from   flask           import Blueprint, current_app, jsonify, redirect, \
                                render_template, url_for
from   packaging.utils import canonicalize_name as normalize
from   .dbutil         import rdepends_query
from   .models         import EntryPoint, EntryPointGroup, Project, Version, \
                                Wheel, WheelData, db
from   .util           import json_response

web = Blueprint('web', __name__)

from . import macros  # noqa

def canonicalize_project_url(f):
    """
    A decorator for views that take a ``project`` parameter; if the project
    name is not in normalized form, a 301 redirect is issued.  This also allows
    the decorated views to skip the call to `normalize()` when fetching the
    `Project` object from the database.
    """
    @wraps(f)
    def wrapped(project):
        normproj = normalize(project)
        if normproj != project:
            return redirect(url_for('.'+f.__name__, project=normproj), code=301)
        else:
            return f(normproj)
    return wrapped

@web.route('/')
@web.route('/index.html')
def index():
    """ The main page """
    proj_qty = db.session.query(db.func.count(Project.id.distinct()))\
                         .join(Version).join(Wheel).join(WheelData).scalar()
    whl_qty = db.session.query(WheelData).count()
    epg_qty = db.session.query(EntryPointGroup).count()
    return render_template(
        'index.html',
        proj_qty = proj_qty,
        whl_qty  = whl_qty,
        epg_qty  = epg_qty,
    )

@web.route('/wheels.html')
def wheel_list():
    """ A list of all wheels with data; for testing purposes only """
    per_page = current_app.config["WHEELODEX_WHEELS_PER_PAGE"]
    wheels = db.session.query(Wheel).join(Version).join(Project)\
                       .filter(Wheel.data.has())\
                       .order_by(
                            Project.name.asc(),
                            Version.ordering.asc(),
                            Wheel.ordering.desc(),
                       ).paginate(per_page=per_page)
    return render_template('wheel_list.html', wheels=wheels)

@web.route('/<wheel>.html')
def wheel_data(wheel):
    """ A display of the data for a given wheel """
    whl = db.session.query(Wheel).filter(Wheel.filename == wheel + '.whl')\
                    .first_or_404()
    return render_template('wheel_data.html', whl=whl)

@web.route('/projects/')
def project_list():
    """
    A list of all projects with wheels with data, along with summaries
    extracted from those wheels
    """
    per_page = current_app.config["WHEELODEX_PROJECTS_PER_PAGE"]
    ### TODO: Speed up this query!
    subq1 = db.session.query(
        Version.id,
        Version.project_id,
        Version.ordering,
        db.func.max(Wheel.ordering).label('max_wheel'),
    ).join(Wheel).join(WheelData).group_by(Version.id).subquery()
    subq2 = db.session.query(
        subq1.c.project_id,
        db.func.max(subq1.c.ordering).label('max_version'),
    ).group_by(subq1.c.project_id).subquery()
    q = db.session.query(Project.name, Project.display_name, WheelData.summary)\
                  .join(Version)\
                  .join(subq2, (Project.id == subq2.c.project_id)
                         & (Version.ordering == subq2.c.max_version))\
                  .join(Wheel)\
                  .join(subq1, (Version.id == subq1.c.id)
                         & (Wheel.ordering == subq1.c.max_wheel))\
                  .join(WheelData)\
                  .order_by(Project.name.asc())\
                  .cte()
    # The query needs to be converted to a CTE with the ORDER BY on the inside
    # and paginate's LIMIT on the outside; otherwise, PostgreSQL's notorious
    # optimization problems with ORDER BY + LIMIT will kick in, and the query
    # will take two and a half minutes to run.
    projects = db.session.query(q).paginate(per_page=per_page)
    return render_template('project_list.html', projects=projects)

@web.route('/projects/<project>/')
@canonicalize_project_url
def project(project):
    """
    A display of the data for a given project, including its "best wheel"
    """
    p = db.session.query(Project).filter(Project.name == project).first_or_404()
    rdeps_qty = rdepends_query(p).count()
    whl = p.best_wheel
    if whl is not None:
        return render_template(
            'wheel_data.html',
            whl          = whl,
            rdepends_qty = rdeps_qty,
            all_wheels   = p.versions_wheels_grid(),
        )
    else:
        return render_template(
            'project_nowheel.html',
            project      = p,
            rdepends_qty = rdeps_qty,
        )

@web.route('/projects/<project>/rdepends/')
@canonicalize_project_url
def rdepends(project):
    """ A list of reverse dependencies for a project """
    per_page = current_app.config["WHEELODEX_RDEPENDS_PER_PAGE"]
    p = db.session.query(Project).filter(Project.name == project).first_or_404()
    rdeps = rdepends_query(p).order_by(Project.name.asc())\
                             .paginate(per_page=per_page)
    return render_template(
        'rdepends.html',
        project  = p.display_name,
        rdepends = rdeps,
    )

@web.route('/entry-points/')
def entry_point_groups():
    """
    A list of all entry point groups (excluding those without any entry points)
    """
    per_page = current_app.config["WHEELODEX_ENTRY_POINT_GROUPS_PER_PAGE"]
    ### TODO: Use preferred wheel (or at least weed out duplicate
    ### Project-EntryPoint.name pairs):
    groups = db.session.query(
                            EntryPointGroup.name,
                            EntryPointGroup.summary,
                            db.func.COUNT(EntryPoint.id),
                        )\
                       .join(EntryPoint)\
                       .group_by(EntryPointGroup)\
                       .order_by(EntryPointGroup.name.asc())\
                       .paginate(per_page=per_page)
    return render_template('entry_point_groups.html', groups=groups)

@web.route('/entry-points/<group>/')
def entry_point(group):
    """
    A list of all entry points in a given group and the packages that define
    them
    """
    ep_group = db.session.query(EntryPointGroup)\
                         .filter(EntryPointGroup.name == group)\
                         .first_or_404()
    per_page = current_app.config["WHEELODEX_ENTRY_POINTS_PER_PAGE"]
    ### TODO: Use preferred wheel (or at least weed out duplicate lines):
    project_eps = db.session.query(Project.display_name, EntryPoint.name)\
                            .join(Version).join(Wheel).join(WheelData)\
                            .join(EntryPoint)\
                            .filter(EntryPoint.group == ep_group)\
                            .order_by(
                                Project.name.asc(), EntryPoint.name.asc()
                            ).paginate(per_page=per_page)
    return render_template(
        'entry_point.html',
        ep_group    = ep_group,
        project_eps = project_eps,
    )

@web.route('/json/projects/<project>')
@canonicalize_project_url
def project_json(project):
    """
    A JSON view of the names of all known wheels (with links) for the given
    project and whether they have data, organized by version
    """
    p = db.session.query(Project).filter(Project.name == project).first_or_404()
    response = OrderedDict()
    for v, wheels in p.versions_wheels_grid():
        lst = []
        for w,d in wheels:
            lst.append({
                "filename": w.filename,
                "has_data": d,
                "href": url_for('.wheel_json', wheel=w.filename),
            })
        response[v] = lst
    return jsonify(response)

@web.route('/json/projects/<project>/data')
@canonicalize_project_url
def project_data_json(project):
    """ A JSON view of the data for a given project's best wheel """
    p = db.session.query(Project).filter(Project.name == project).first_or_404()
    ### TODO: Should this use preferred_wheel instead?  The URL does say
    ### "data"...
    whl = p.best_wheel
    if whl is not None:
        return jsonify(whl.as_json())
    else:
        return json_response(
            {"message": "No wheels found for project"},
            status_code=404,
        )

@web.route('/json/projects/<project>/rdepends')
@canonicalize_project_url
def project_rdepends_json(project):
    """ A JSON view of the reverse dependencies for a project """
    per_page = current_app.config["WHEELODEX_RDEPENDS_PER_PAGE"]
    p = db.session.query(Project).filter(Project.name == project).first_or_404()
    rdeps = rdepends_query(p).order_by(Project.name.asc())\
                             .paginate(per_page=per_page)
    return jsonify({
        "items": [{
            "name": proj.display_name,
            "href": url_for('.project_json', project=proj.name),
        } for proj in rdeps.items],
        "total": rdeps.total,
        "links": {
            "next": url_for(
                '.project_rdepends_json',
                project = project,
                page    = rdeps.next_num,
            ) if rdeps.has_next else None,
            "prev": url_for(
                '.project_rdepends_json',
                project = project,
                page    = rdeps.prev_num,
            ) if rdeps.has_prev else None,
        },
    })

@web.route('/json/wheels/<wheel>.json')
def wheel_json(wheel):
    """ A JSON view of the data for a given wheel """
    whl = db.session.query(Wheel).filter(Wheel.filename == wheel).first_or_404()
    return jsonify(whl.as_json())
