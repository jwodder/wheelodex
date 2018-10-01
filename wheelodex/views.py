from flask           import Blueprint, current_app, jsonify, render_template
from packaging.utils import canonicalize_name as normalize
from .db             import Project, Version, Wheel, db

web = Blueprint('web', __name__)

from .     import macros  # noqa

@web.route('/wheels.html')
def wheel_list():
    per_page = current_app.config["WHEELODEX_WHEELS_PER_PAGE"]
    wheels = db.session.query(Wheel).join(Version).join(Project)\
                       .filter(Wheel.data.has())\
                       .order_by(
                            Project.name.asc(),
                            Version.ordering.asc(),
                            Wheel.ordering.desc(),
                       ).paginate(per_page=per_page)
    return render_template('wheel_list.html', wheels=wheels)

@web.route('/<wheel>.json')
def wheel_json(wheel):
    whl = db.session.query(Wheel).filter(Wheel.filename == wheel + '.whl')\
                    .first_or_404()
    return jsonify(whl.as_json())

@web.route('/<wheel>.html')
def wheel_html(wheel):
    whl = db.session.query(Wheel).filter(Wheel.filename == wheel + '.whl')\
                    .first_or_404()
    return render_template('wheel_data.html', whl=whl)

@web.route('/project/<name>.html')
def project(name):
    p = db.session.query(Project).filter(Project.name == normalize(name))\
                  .first_or_404()
    whl = p.preferred_wheel
    if whl is not None:
        return render_template('wheel_data.html', whl=whl)
    else:
        return 'No data available'

@web.route('/entry-point/<group>.html')
def entry_point(group):
    ### TODO
    return 'TODO'
