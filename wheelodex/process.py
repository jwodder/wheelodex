import logging
import os
import os.path
from   tempfile          import TemporaryDirectory
import traceback
from   requests_download import download
from   .inspect          import inspect_wheel
from   .models           import db
from   .dbutil           import iterqueue
from   .util             import USER_AGENT

log = logging.getLogger(__name__)

def process_queue(max_wheel_size=None):
    with TemporaryDirectory() as tmpdir:
        for whl in iterqueue(max_wheel_size=max_wheel_size):
            try:
                about = process_wheel(
                    filename = whl.filename,
                    url      = whl.url,
                    size     = whl.size,
                    md5      = whl.md5,
                    sha256   = whl.sha256,
                    tmpdir   = tmpdir,
                )
                whl.set_data(about)
                # Some errors in inserting data aren't raised until we actually
                # try to insert by calling commit(), so include the commit()
                # under the `try`.
                db.session.commit()
            except Exception:
                # rollback() needs to be called before log.exception() or else
                # SQLAlchemy gets all complainy.
                db.session.rollback()
                log.exception('Error processing %s', whl.filename)
                whl.add_error(traceback.format_exc())
                db.session.commit()

def process_wheel(filename, url, size, md5, sha256, tmpdir):
    fpath = os.path.join(tmpdir, filename)
    log.info('Downloading %s from %s ...', filename, url)
    # Write "user-agent" in lowercase so it overrides requests_download's
    # header correctly:
    download(url, fpath, headers={"user-agent": USER_AGENT})
    log.info('Inspecting %s ...', filename)
    try:
        about = inspect_wheel(fpath)
    finally:
        os.remove(fpath)
    if about["file"]["size"] != size:
        log.error('Wheel %s: size mismatch: PyPI reports %d, got %d',
                  size, about["file"]["size"])
        raise ValueError('Size mismatch: PyPI reports {}, got {}'
                         .format(size, about["file"]["size"]))
    for alg, expected in [("md5", md5), ("sha256", sha256)]:
        if expected is not None and expected != about["file"]["digests"][alg]:
            log.error(
                'Wheel %s: %s hash mismatch: PyPI reports %s, got %s',
                alg,
                expected,
                about["file"]["digests"][alg],
            )
            raise ValueError(
                '{} hash mismatch: PyPI reports {}, got {}'.format(
                    alg,
                    expected,
                    about["file"]["digests"][alg],
                )
            )
    log.info('Finished inspecting %s', filename)
    return about
