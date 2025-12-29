import functools
import os
from pathlib import Path
import sys
import sysconfig
import tempfile


_module_name = __name__.split('.')[0]

_gstreamer_root = Path(__file__).parent.as_posix()

if sys.prefix == sys.base_prefix:
    _gst_registry_filepath = (
        f'gstreamer-1.0/wheel-registry-{sysconfig.get_python_version()}-{sysconfig.get_platform()}.bin'
    )
    _folder = tempfile.gettempdir() if sys.platform == 'win32' else '~/.cache'
    _gst_registry_10 = Path(_folder, _gst_registry_filepath).expanduser()
else:
    # Localise the registry to the venv
    _gst_registry_filepath = f'gstreamer-1.0/registry-{sysconfig.get_platform()}.bin'
    _folder = 'Temp' if sys.platform == 'win32' else '.cache'
    _gst_registry_10 = Path(sys.prefix, _folder, _gst_registry_filepath)

"""
These paths will be prepended by gstreamer's build_environment
"""
environment = {
    'PATH': f'{_gstreamer_root}/bin',
    'LD_LIBRARY_PATH': f'{_gstreamer_root}/lib',
    'GST_PLUGIN_PATH_1_0': f'{_gstreamer_root}/lib/gstreamer-1.0',
    'GST_PLUGIN_SYSTEM_PATH_1_0': f'{_gstreamer_root}/lib/gstreamer-1.0',
    # No longer valid under sharding
    # 'GSTREAMER_ROOT': _gstreamer_root,
    # Specific to gstreamer_runtime
    'PKG_CONFIG_PATH': [
        f'{_gstreamer_root}/lib/pkgconfig',
        f'{_gstreamer_root}/share/pkgconfig',
    ],
    'XDG_DATA_DIRS': [
        f'{_gstreamer_root}/share',
    ],
    'XDG_CONFIG_DIRS': [
        f'{_gstreamer_root}/etc/xdg',
    ],
    'GST_REGISTRY_1_0': _gst_registry_10.as_posix(),
    'GST_PLUGIN_SCANNER_1_0': f'{_gstreamer_root}/libexec/gstreamer-1.0/gst-plugin-scanner',
    'GI_TYPELIB_PATH': f'{_gstreamer_root}/lib/girepository-1.0',
    # The rest will already be filled by the setup_environment shim
    'PYGI_DLL_DIRS': f'{_gstreamer_root}/bin',
}


@functools.lru_cache()
def gstreamer_env():
    """
    Returns a copy of os.environ, adding all the folders that are necessary
    for GStreamer to load and run successfully.

    This function is cached, so it will not be updated if os.environ changes.
    """

    from gstreamer_plugins import environment as gp_env

    try:
        from gstreamer_cli import environment as gc_env
    except ImportError:
        gc_env = {}
    try:
        from gstreamer_plugins_restricted import environment as gpr_env
    except ImportError:
        gpr_env = {}
    try:
        from gstreamer_plugins_gpl import environment as gp_gpl_env
    except ImportError:
        gp_gpl_env = {}
    try:
        from gstreamer_plugins_gpl_restricted import environment as gp_gplr_env
    except ImportError:
        gp_gplr_env = {}
    try:
        from gstreamer_plugins_runtime import environment as gp_r_env
    except ImportError:
        gp_r_env = {}
    try:
        from gstreamer_plugins_frei0r import environment as gp_f_env
    except ImportError:
        gp_f_env = {}

    try:
        from gstreamer_python import environment as py_env
    except ImportError:
        py_env = {}

    try:
        from gstreamer_gtk import environment as gtk_env
    except ImportError:
        gtk_env = {}

    if sys.platform == 'win32':
        try:
            from gstreamer_msvc_runtime import environment as gp_msvc_env
        except ImportError:
            gp_msvc_env = {}
    else:
        gp_msvc_env = {}

    env = os.environ.copy()

    def prepend(var: str, new_value: str, sep=os.pathsep) -> None:
        old = env.get(var)
        if old:
            env[var] = sep.join([new_value, old])
        else:
            env[var] = new_value

    package_keys = [
        environment.items(),
        gtk_env.items(),
        py_env.items(),
        gp_env.items(),
        gpr_env.items(),
        gp_f_env.items(),
        gp_r_env.items(),
        gp_gpl_env.items(),
        gp_gplr_env.items(),
        gc_env.items(),
        gp_msvc_env.items(),
    ]

    dll_directories = []
    for i in package_keys:
        for k, v in i:
            # PATH is used on win32, and rpath on macOS
            if sys.platform in ('win32', 'darwin') and k == 'LD_LIBRARY_PATH':
                continue
            if k == 'PATH':
                dll_directories.extend(v.split(os.pathsep))
            if isinstance(v, str):
                prepend(k, v)
            else:
                for p in v:
                    prepend(k, p)

    # environment, os.add_dll_directory
    return (env, list(set(dll_directories)))


def setup_python_environment():
    """
    Injects the GStreamer binary folders into the current interpreter's
    environment. On Windows, it also updates the allowed DLL folders list.
    """
    env, dlls = gstreamer_env()

    os.environ.update(env)

    # Just in case -- an import gi; will do it too
    if sys.platform == 'win32':
        for dll in dlls:
            if os.path.exists(dll):
                os.add_dll_directory(dll)

    sys.path.append(env['GST_PYTHONPATH_1_0'])
