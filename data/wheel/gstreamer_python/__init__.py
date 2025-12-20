import os
from pathlib import Path


_module_name = __name__.split('.')[0]

_gstreamer_root = Path(__file__).parent.as_posix()


def _get_site_packages_prefix(base):
    for root, dirs, files in os.walk(base):
        if 'gi' in dirs:
            return root
    raise RuntimeError(f"Couldn't find site-packages prefix inside {base}")


_site_packages_prefix = _get_site_packages_prefix(_gstreamer_root)

"""
These paths will be prepended by gstreamer[cli,gpl]'s build_environment
"""
environment = {
    'PATH': f'{_gstreamer_root}/bin',
    'LD_LIBRARY_PATH': f'{_gstreamer_root}/lib',
    'GI_TYPELIB_PATH': f'{_gstreamer_root}/lib/girepository-1.0',
    'GST_PLUGIN_PATH_1_0': f'{_gstreamer_root}/lib/gstreamer-1.0',
    'GST_PLUGIN_SYSTEM_PATH_1_0': f'{_gstreamer_root}/lib/gstreamer-1.0',
    'GST_PYTHONPATH_1_0': Path(_gstreamer_root, _site_packages_prefix).as_posix(),
}
