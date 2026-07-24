from pathlib import Path


_module_name = __name__.split('.')[0]

_gstreamer_root = Path(__file__).parent.as_posix()

"""
These paths will be prepended by gstreamer's build_environment
"""
environment = {
    'PATH': f'{_gstreamer_root}/bin',
    'LD_LIBRARY_PATH': f'{_gstreamer_root}/lib',
    'GIO_EXTRA_MODULES': f'{_gstreamer_root}/lib/gio/modules',
}
