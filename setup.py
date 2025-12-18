import os
import shutil
from setuptools import setup, find_packages
from setuptools.command import sdist as setuptools_sdist
from setuptools.command.build_py import build_py

# Import logging for setup commands
try:
    from setuptools import logging
except ImportError:
    # Fallback for older setuptools
    import logging

    logging.basicConfig(level=logging.INFO)

log = logging.getLogger(__name__)


# Get version directly from enums.py without importing it
def get_version():
    version_file = os.path.join(os.path.dirname(__file__), 'cerbero', 'enums.py')
    with open(version_file) as f:
        for line in f:
            if line.startswith('CERBERO_VERSION'):
                return line.split('=')[1].strip().strip('\'"')
    return '0.0.0'


CERBERO_VERSION = get_version()


# Utility function to read the README file.
def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


# Extended sdist for bundlesource command compatibility
class extended_sdist(setuptools_sdist.sdist):
    user_options = setuptools_sdist.sdist.user_options + [
        ('source-dirs=', None, 'Comma-separated list of source directories to add to the package'),
        ('package=', None, 'Specific package to include, other packages are not included'),
        ('recipe=', None, 'Specific recipe to include, other recipes are not included'),
    ]

    def initialize_options(self):
        self.source_dirs = []
        setuptools_sdist.sdist.initialize_options(self)

    def finalize_options(self):
        self.ensure_string_list('source_dirs')
        setuptools_sdist.sdist.finalize_options(self)

    def make_release_tree(self, base_dir, files):
        setuptools_sdist.sdist.make_release_tree(self, base_dir, files)
        if self.source_dirs:
            for d in self.source_dirs:
                src = d.rstrip().rstrip(os.sep)
                dest = os.path.join(base_dir, 'sources', os.path.basename(src))
                log.info('Copying %s -> %s', src, dest)
                if not self.dry_run:
                    if os.path.exists(dest):
                        shutil.rmtree(dest)
                    shutil.copytree(src, dest)


# Custom build_py to copy data directories into cerbero_share package
class build_with_data(build_py):
    """Custom build that copies data directories into cerbero_share package"""

    def run(self):
        # Run the standard build first
        build_py.run(self)

        # Remove any top-level data directories that setuptools might have copied
        for unwanted in ['recipes', 'packages', 'config', 'data', 'tools', 'ci', 'venv']:
            unwanted_dir = os.path.join(self.build_lib, unwanted)
            if os.path.exists(unwanted_dir):
                log.info(f'Removing unwanted {unwanted}/ from build')
                shutil.rmtree(unwanted_dir)

        # Create cerbero_share package directory
        package_dir = os.path.join(self.build_lib, 'cerbero_share')
        os.makedirs(package_dir, exist_ok=True)

        # Create __init__.py for cerbero_share package
        init_file = os.path.join(package_dir, '__init__.py')
        with open(init_file, 'w') as f:
            f.write('# This package contains data files (recipes, packages, config, data, tools)\n')
            f.write('# that are installed alongside the cerbero Python package.\n')

        # Data directories to copy into cerbero_share
        data_dirs = ['recipes', 'packages', 'config', 'data', 'tools']

        # Copy each data directory
        for data_dir in data_dirs:
            src = os.path.join(os.path.dirname(__file__), data_dir)
            if not os.path.exists(src):
                raise FileNotFoundError(f'Required data directory not found: {src}')
            dest = os.path.join(package_dir, data_dir)
            if os.path.exists(dest):
                shutil.rmtree(dest)
            log.info(f'Copying {data_dir}/ -> cerbero_share/{data_dir}/')
            shutil.copytree(src, dest)


setup(
    name='cerbero',
    version=CERBERO_VERSION,
    author='Andoni Morales',
    author_email='amorales@fluendo.com',
    description=('Multi platform build system for Open Source projects'),
    license='LGPL',
    url='http://gstreamer.freedesktop.org/',
    packages=find_packages(exclude=['tests', 'test', 'recipes', 'packages', 'config', 'data', 'tools'])
    + ['cerbero_share'],
    py_modules=[],  # Don't auto-discover top-level modules
    long_description=read('README.md'),
    long_description_content_type='text/markdown',
    zip_safe=False,
    include_package_data=True,
    entry_points={
        'console_scripts': [
            'cerbero=cerbero.main:main',
        ],
    },
    classifiers=[
        'License :: OSI Approved :: GNU Lesser General Public License v2 or later (LGPLv2+)',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
    ],
    python_requires='>=3.9',
    cmdclass={
        'sdist': extended_sdist,
        'build_py': build_with_data,
    },
)
