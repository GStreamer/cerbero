import json
import os
import platform
import setuptools
from setuptools.dist import Distribution
from setuptools.command.build_py import build_py
from setuptools.command.bdist_wheel import bdist_wheel


desc = json.load(open('gstreamer_vendor.json', 'r', encoding='utf-8'))

package_name = desc['package_name']


class BinaryDistribution(Distribution):
    def has_ext_modules(self):
        # FIXME: ask pycairo/g-i/gstpython to use Stable ABI
        # To do this, we need to convert all uses of the Python API
        # to match the Limited API; usually means dropping all macros
        # and using functions whenever possible.
        # See https://docs.python.org/3/c-api/stable.html#limited-c-api
        #
        # This is (perhaps) easy with PyCairo/gstpython but definitely not with
        # G-I because they define new Python types on the stack.
        # See https://gitlab.gnome.org/GNOME/pygobject/-/blob/main/gi/pygi-util.h#L32
        # and https://doc.qt.io/qtforpython-6/developer/limited_api.html for
        # a gist of what porting would imply.
        return package_name == 'gstreamer_python'

    def has_c_libraries(self):
        return package_name not in ('gstreamer', 'gstreamer_python')


class InjectGStreamerWheels(build_py):
    IMPORT_SHIM = """import sys; import gstreamer_runtime; gstreamer_runtime.setup_python_environment();
"""

    def run(self):
        super().run()
        sitecustomize_path = os.path.join(self.build_lib, f'{package_name}.pth')
        with open(sitecustomize_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(self.IMPORT_SHIM)


class MakeStableAbiWheel(bdist_wheel):
    def finalize_options(self):
        # XXX: See BinaryDistribution above
        # This ensures that we only generate Python-version-specific wheels for
        # wheels with shared libraries that use Python's C API.
        if package_name != 'gstreamer_python':
            self.py_limited_api = 'cp39'
            # Make it so that bdist_wheel generates the right platform name for
            # wheels that do not link to Python
            if platform.system() == 'Darwin':
                self.plat_name = 'macosx_10_13_universal2'
        super().finalize_options()


cmdclass = {'bdist_wheel': MakeStableAbiWheel}

if desc['needs_environment']:
    cmdclass['build_py'] = InjectGStreamerWheels  # type: ignore


# https://setuptools.pypa.io/en/latest/references/keywords.html
# https://setuptools.pypa.io/en/latest/userguide/pyproject_config.html
setuptools.setup(
    name=desc['package_name'],
    description=desc['description'],
    url=desc['url'],
    author=desc['vendor'],
    license=desc['spdx_license'],
    classifiers=desc['classifiers'],
    install_requires=desc['install_requires'],
    extras_require=desc['extras_require'],
    distclass=BinaryDistribution,
    cmdclass=cmdclass,
    version=desc['version'],
    include_package_data=True,
    python_requires=desc['python_version'],
    entry_points=desc['entrypoints'],
    libraries=[],
)
