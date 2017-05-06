import os
import sys
import shutil
from setuptools import setup, find_packages
from setuptools.command import sdist as setuptools_sdist
from cerbero.utils import shell
from distutils.dir_util import copy_tree
import distutils.log

sys.path.insert(0, './cerbero')


# Utility function to read the README file.
def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()


# Utility function to parse directories
def parse_dir(dirpath, extension=None):
    if os.path.exists('.git'):
        files = shell.check_call('git ls-files %s' % dirpath).split('\n')
        files.remove('')
    else:
        files = shell.check_call('find %s -type f' % dirpath).split('\n')
        files.remove('')
    if extension is None:
        return files
    return [f for f in files if f.endswith(extension)]


# Utility function to create the list of data files
def datafiles(prefix):
    files = []
    datadir = os.path.join(prefix, 'share', 'cerbero')
    for dirname, extension in [('recipes', '.recipe'), ('packages', '.package')]:
        for f in parse_dir(dirname, extension):
            files.append((os.path.join(datadir, dirname), [f]))
    for dirname in ['config']:
        for f in parse_dir(dirname):
            files.append((os.path.join(datadir, dirname), [f]))
    for dirname in ['data']:
        for f in parse_dir(dirname):
            dirpath = os.path.split(f.split('/', 1)[1])[0]
            files.append((os.path.join(datadir, dirpath), [f]))
    return files

# Intercept packages and recipes
packages = [x[len('--package='):] for x in sys.argv
            if x.startswith('--package=')]
recipes = [x[len('--recipe='):] for x in sys.argv if x.startswith('--recipe=')]
if len(packages) == 0:
    packages = None
if len(recipes) == 0:
    recipes = None
sys.argv = [x for x in sys.argv if not x.startswith('--package=') and
            not x.startswith('--recipe=')]


#Fill manifest
shutil.copy('MANIFEST.in.in', 'MANIFEST.in')
with open('MANIFEST.in', 'a+') as f:
    for dirname in ['data', 'config', 'tools']:
        f.write('\n'.join(['include %s' % x for x in parse_dir(dirname)]))
        f.write('\n')

    for (dirname, suffix) in [('packages', '.package'), ('recipes', '.recipe')]:
        filenames = parse_dir(dirname)
        requested = globals()[dirname]
        if requested:
            requested_filenames = tuple([os.sep + x + suffix for x in requested])

            # Add special directories
            if dirname == 'packages':
                requested_dir = requested + ['gstreamer-1.0']
            else:
                requested_dir = requested + ['build-tools', 'toolchain']
            requested_directories = tuple(os.path.join(dirname, x, "")
                                     for x in requested_dir)

            filenames = [p for p in filenames
                         if p.startswith(requested_directories) or
                         p.endswith(requested_filenames) or
                         p.endswith('.py')]

            missing_files = [p for p in requested_filenames if
                             not [True for m in filenames if m.endswith(p)]]
            assert not missing_files, \
                "Not all %s from the command line (%s) exist" % \
                (dirname, ", ".join(missing_files))
        f.write('\n'.join(['include %s' % x for x in filenames]))
        f.write('\n')


# Intercept prefix
prefix = [x for x in sys.argv if x.startswith('--prefix=')]
if len(prefix) == 1:
    prefix = prefix[0].split('--prefix=')[1]
else:
    prefix = '/usr/local'

class extended_sdist(setuptools_sdist.sdist):
    user_options = setuptools_sdist.sdist.user_options + [
        ('source-dirs=', None,
         "Comma-separated list of source directories to add to the package"),
        ('package=', None,
         "Specific package to include, other packages are not included"),
        ('recipe=', None,
         "Specific recipe to include, other recipes are not included"),
    ]

    def initialize_options(self):
        self.source_dirs = []
        setuptools_sdist.sdist.initialize_options(self)

    def finalize_options(self):
        self.ensure_string_list('source_dirs')
        setuptools_sdist.sdist.finalize_options(self)

    def make_release_tree(self, base_dir, files):
        setuptools_sdist.sdist.make_release_tree(self, base_dir, files)
        for d in self.source_dirs:
            src = d.rstrip().rstrip(os.sep)
            dest = os.path.join(base_dir, 'sources', os.path.basename(src))
            distutils.log.info("Copying %s -> %s", src, dest)
            copy_tree(src, dest, update=not self.force, verbose=0,
                      dry_run=self.dry_run)

setup(
    name = "cerbero",
    version = "1.13.0.1",
    author = "Andoni Morales",
    author_email = "amorales@fluendo.com",
    description = ("Multi platform build system for Open Source projects"),
    license = "LGPL",
    url = "http://gstreamer.freedesktop.org/",
    packages = find_packages(exclude=['tests']),
    long_description=read('README'),
    zip_safe = False,
    include_package_data=True,
    data_files = datafiles(prefix),
    entry_points = """
        [console_scripts]
        cerbero = cerbero.main:main""",
    classifiers=[
        "License :: OSI Approved :: LGPL License",
    ],
    cmdclass = {
        'sdist' : extended_sdist
    }
)
