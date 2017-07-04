from   headerparser import HeaderParser, BOOL
from   ..flags      import Flags

infoparser = HeaderParser()
# NOTE: WHEEL files generated by `wheel` (but not by `flit`) end with a blank
# line, which headerparser interprets as the start of an empty body.
infoparser.add_field('Wheel-Version', required=True)
infoparser.add_field('Generator', required=True)
    ### Split Generator into software name and version?
infoparser.add_field('Root-Is-Purelib', required=True, type=BOOL)
infoparser.add_field('Tag', required=True, multiple=True)
infoparser.add_field('Build')  ### type=int ???
infoparser.add_additional(
    action=lambda d, name, _: d.setdefault("extra_fields", set()).add(name)
)

def parse_wheel_info(fp):
    """ Parsing :file:`{distribution}-{version}.dist-info/WHEEL` files """
    wi = infoparser.parse_file(fp)
    ### TODO: Warn if Wheel-Version >1.0, error if >=2.0
    wheel_info = {k.lower().replace('-', '_'): v for k,v in wi.items()}
    ### Log extra_fields?
    ### Remove null/empty fields???
    flags = set()
    if wi.body is not None and wi.body.strip():
        flags.add(Flags.BODY_IN_WHEEL_INFO)
        ### Store body somewhere?
    return wheel_info, flags
