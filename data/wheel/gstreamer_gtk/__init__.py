from pathlib import Path


_module_name = __name__.split('.')[0]

_gstreamer_root = Path(__file__).parent.as_posix()


"""
These paths will be prepended by gstreamer's build_environment
"""
environment = {
    'PYTHONPATH': Path(__file__).parent.parent.as_posix(),
    'PATH': f'{_gstreamer_root}/bin',
    'LD_LIBRARY_PATH': f'{_gstreamer_root}/lib',
    'GI_TYPELIB_PATH': f'{_gstreamer_root}/lib/girepository-1.0',
    'GST_PLUGIN_PATH_1_0': f'{_gstreamer_root}/lib/gstreamer-1.0',
    'GST_PLUGIN_SYSTEM_PATH_1_0': f'{_gstreamer_root}/lib/gstreamer-1.0',
}
