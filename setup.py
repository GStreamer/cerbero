import os
import sys
import shutil
from setuptools import setup, find_packages
from cerbero.utils import shell

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


#Fill manifest
shutil.copy('MANIFEST.in.in', 'MANIFEST.in')
with open('MANIFEST.in', 'a+') as f:
    for dirname in ['recipes', 'packages', 'data', 'config', 'tools']:
        f.write('\n'.join(['include %s' % x for x in parse_dir(dirname)]))
        f.write('\n')


# Intercept prefix
prefix = [x for x in sys.argv if x.startswith('--prefix=')]
if len(prefix) == 1:
    prefix = prefix[0].split('--prefix=')[1]
else:
    prefix = '/usr/local'


setup(
    name = "cerbero",
    version = "0.1.0",
    author = "Andoni Morales",
    author_email = "amorales@fluendo.com",
    description = ("Multi platform build system for Open Source projects"),
    license = "LGPL",
    url = "http://gstreamer.com",
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
)
