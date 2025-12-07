import json
import os
import setuptools
from setuptools.dist import Distribution
from setuptools.command.build_py import build_py


desc = json.load(open('gstreamer_vendor.json', 'r', encoding='utf-8'))

package_name = desc['package_name']


class BinaryDistribution(Distribution):
    def has_ext_modules(self):
        return True


class InjectGStreamerWheels(build_py):
    IMPORT_SHIM = """import sys; import gstreamer_runtime; gstreamer_runtime.setup_python_environment();
"""

    def run(self):
        super().run()
        sitecustomize_path = os.path.join(self.build_lib, f'{package_name}.pth')
        with open(sitecustomize_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(self.IMPORT_SHIM)

cmdclass = {}

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
