from pathlib import Path
import sysconfig


_module_name = __name__.split('.')[0]

_gstreamer_root = Path(sysconfig.get_path('platlib'), _module_name).as_posix()

"""
These paths will be prepended by gstreamer[cli,gpl]'s build_environment
"""
environment = {
    'PATH': f'{_gstreamer_root}/bin',
}
