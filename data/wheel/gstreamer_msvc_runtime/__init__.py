from pathlib import Path


_module_name = __name__.split('.')[0]

_gstreamer_root = Path(__file__).parent.as_posix()

"""
These paths will be prepended by gstreamer[cli,gpl]'s build_environment
"""
environment = {
    'PATH': f'{_gstreamer_root}/bin',
}
