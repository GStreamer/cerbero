import functools
import os
from pathlib import Path
import sys
import sysconfig
import tempfile


@functools.lru_cache()
def build_gstreamer_env():
    env = os.environ.copy()

    if env.get('GST_PYTHONPATH_1_0'):
        return env

    platlibdir = Path(sysconfig.get_path('platlib'))

    site_packages_prefix = platlibdir.relative_to(sys.prefix)

    gstreamer_root = Path(platlibdir, 'gstreamer').as_posix()

    gstreamer_lib_site_packages = gstreamer_root / site_packages_prefix

    def prepend(var: str, new_value: str, sep=os.pathsep) -> None:
        old = env.get(var)
        if old:
            env[var] = sep.join([new_value, old])
        else:
            env[var] = new_value

    def prepend_flag(var: str, flag: str) -> None:
        old = env.get(var)
        if old:
            env[var] = ' '.join([flag, old])
        else:
            env[var] = flag

    env['GSTREAMER_ROOT'] = gstreamer_root

    prepend('PATH', f'{gstreamer_root}/bin')
    prepend('LD_LIBRARY_PATH', f'{gstreamer_root}/lib')
    prepend('PKG_CONFIG_PATH', f'{gstreamer_root}/lib/pkgconfig')
    prepend('PKG_CONFIG_PATH', f'{gstreamer_root}/share/pkgconfig')
    prepend('XDG_DATA_DIRS', f'{gstreamer_root}/share')
    prepend('XDG_CONFIG_DIRS', f'{gstreamer_root}/etc/xdg')

    if sys.prefix == sys.base_prefix:
        _gst_registry_filepath = (
            f'gstreamer-1.0/wheel-registry-{sysconfig.get_python_version()}-{sysconfig.get_platform()}.bin'
        )
        _folder = tempfile.gettempdir() if sys.platform == 'win32' else '~/.cache'
        gstregistry10 = Path(_folder, _gst_registry_filepath).expanduser()
    else:
        # Localise the registry to the venv
        _gst_registry_filepath = f'gstreamer-1.0/registry-{sysconfig.get_platform()}.bin'
        _folder = 'Temp' if sys.platform == 'win32' else '.cache'
        gstregistry10 = Path(sys.prefix, _folder, _gst_registry_filepath)
    env['GST_REGISTRY_1_0'] = gstregistry10.as_posix()

    env['GST_PLUGIN_SCANNER_1_0'] = f'{gstreamer_root}/libexec/gstreamer-1.0/gst-plugin-scanner'

    env['GST_PLUGIN_PATH_1_0'] = f'{gstreamer_root}/lib/gstreamer-1.0'

    env['GST_PLUGIN_SYSTEM_PATH_1_0'] = f'{gstreamer_root}/lib/gstreamer-1.0'

    env['GST_PYTHONPATH_1_0'] = gstreamer_lib_site_packages.as_posix()

    prepend('PYTHONPATH', env['GST_PYTHONPATH_1_0'])

    prepend_flag('CFLAGS', f'-I{gstreamer_root}/include')
    prepend_flag('CXXFLAGS', f'-I{gstreamer_root}/include')
    prepend_flag('CPPFLAGS', f'-I{gstreamer_root}/include')
    prepend_flag('LDFLAGS', f'-L{gstreamer_root}/lib')

    env['GIO_EXTRA_MODULES'] = f'{gstreamer_root}/lib/gio/modules'
    env['GI_TYPELIB_PATH'] = f'{gstreamer_root}/lib/girepository-1.0'

    return env
