import json
import os
import setuptools
from setuptools.command.build_py import build_py


class TagWithPythonVersion(setuptools.Distribution):
    def has_ext_modules(self):
        return True


class InjectGStreamerWheels(build_py):
    GSTREAMER_IMPORT = r"""import sys; import gstreamer; gstreamer.setup_python_environment();
"""

    def run(self):
        super().run()
        sitecustomize_path = os.path.join(self.build_lib, 'gstreamer.pth')
        with open(sitecustomize_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(self.GSTREAMER_IMPORT)


gstreamer_vendor = json.load(open('gstreamer_vendor.json', 'r', encoding='utf-8'))

# https://setuptools.pypa.io/en/latest/references/keywords.html
# https://setuptools.pypa.io/en/latest/userguide/pyproject_config.html
setuptools.setup(
    name=gstreamer_vendor['package_name'],
    description=gstreamer_vendor['description'],
    url=gstreamer_vendor['url'],
    author=gstreamer_vendor['vendor'],
    license=gstreamer_vendor['spdx_license'],
    classifiers=gstreamer_vendor['classifiers'],
    # typing_extensions required on macOS for g-i overrides
    install_requires=['setuptools >= 80.9.0', 'typing_extensions >= 4.15.0'],
    distclass=TagWithPythonVersion,
    cmdclass={'build_py': InjectGStreamerWheels},
    version=gstreamer_vendor['version'],
    include_package_data=True,
    python_requires=gstreamer_vendor['python_version'],
    entry_points=gstreamer_vendor['entrypoints'],
)
