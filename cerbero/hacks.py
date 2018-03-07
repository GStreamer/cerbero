# cerbero - a multi-platform build system for Open Source software
# Copyright (C) 2012 Andoni Morales Alastruey <ylatuya@gmail.com>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Library General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Library General Public License for more details.
#
# You should have received a copy of the GNU Library General Public
# License along with this library; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place - Suite 330,
# Boston, MA 02111-1307, USA.

import os
import sys


### XML Hacks ###

import re
import StringIO
from xml.dom import minidom
from cerbero.utils import etree
oldwrite = etree.ElementTree.write


def pretify(string, pretty_print=True):
    parsed = minidom.parseString(string)
    # See:http://www.hoboes.com/Mimsy/hacks/geektool-taskpaper-and-xml/
    fix = re.compile(r'((?<=>)(\n[\t]*)(?=[^<\t]))|(?<=[^>\t])(\n[\t]*)(?=<)')
    return re.sub(fix, '', parsed.toprettyxml())


def write(self, file_or_filename, encoding=None, pretty_print=False):
    if not pretty_print:
        return oldwrite(self, file_or_filename, encoding)
    tmpfile = StringIO.StringIO()
    oldwrite(self, tmpfile, encoding)
    tmpfile.seek(0)
    if hasattr(file_or_filename, "write"):
        out_file = file_or_filename
    else:
        out_file = open(file_or_filename, "wb")
    out_file.write(pretify(tmpfile.read()))
    if not hasattr(file_or_filename, "write"):
        out_file.close()


etree.ElementTree.write = write


### Windows Hacks ###

# On windows, python transforms all enviroment variables to uppercase,
# but we need lowercase ones to override configure options like
# am_cv_python_platform

environclass = os.environ.__class__
import UserDict


class _Environ(environclass):

    def __init__(self, environ):
        UserDict.UserDict.__init__(self)
        self.data = {}
        for k, v in environ.items():
            self.data[k] = v

    def __setitem__(self, key, item):
        os.putenv(key, item)
        self.data[key] = item

    def __getitem__(self, key):
        return self.data[key]

    def __delitem__(self, key):
        os.putenv(key, '')
        del self.data[key]

    def pop(self, key, *args):
        os.putenv(key, '')
        return self.data.pop(key, *args)

    def has_key(self, key):
        return key in self.data

    def __contains__(self, key):
        return key in self.data

    def get(self, key, failobj=None):
        return self.data.get(key, failobj)


# we don't want backlashes in paths as it breaks shell commands

oldexpanduser = os.path.expanduser
oldabspath = os.path.abspath
oldrealpath = os.path.realpath


def join(*args):
    return '/'.join(args)


def expanduser(path):
    return oldexpanduser(path).replace('\\', '/')


def abspath(path):
    return oldabspath(path).replace('\\', '/')


def realpath(path):
    return oldrealpath(path).replace('\\', '/')

if sys.platform.startswith('win'):
    os.environ = _Environ(os.environ)
    os.path.join = join
    os.path.expanduser = expanduser
    os.path.abspath = abspath
    os.path.realpath = realpath

import stat
import shutil
from shutil import rmtree as shutil_rmtree
from cerbero.utils.shell import call as shell_call

def rmtree(path, ignore_errors=False, onerror=None):
    '''
    shutil.rmtree often fails with access denied. On Windows this happens when
    a file is readonly. On Linux this can happen when a directory doesn't have
    the appropriate permissions (Ex: chmod 200) and many other cases.
    '''
    def force_removal(func, path, excinfo):
        '''
        This is the only way to ensure that readonly files are deleted by
        rmtree on Windows. See: http://bugs.python.org/issue19643
        '''
        # Due to the way 'onerror' is implemented in shutil.rmtree, errors
        # encountered while listing directories cannot be recovered from. So if
        # a directory cannot be listed, shutil.rmtree assumes that it is empty
        # and it tries to call os.remove() on it which fails. This is just one
        # way in which this can fail, so for robustness we just call 'rm' if we
        # get an OSError while trying to remove a specific path.
        # See: http://bugs.python.org/issue8523
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except OSError:
            shell_call('rm -rf ' + path)
    # We try to not use `rm` because on Windows because it's about 20-30x slower
    if not onerror:
        shutil_rmtree(path, ignore_errors, onerror=force_removal)
    else:
        shutil_rmtree(path, ignore_errors, onerror)

shutil.rmtree = rmtree

### OS X Hacks ###

# use cURL to download instead of wget

import cerbero.utils.shell
# wget shipped with msys fails with an SSL error on github URLs
# https://githubengineering.com/crypto-removal-notice/
if not sys.platform.startswith('win') and cerbero.utils.shell.which('wget'):
    cerbero.utils.shell.download = cerbero.utils.shell.download_wget
elif cerbero.utils.shell.which('curl'):
    cerbero.utils.shell.download = cerbero.utils.shell.download_curl
else:
    # This is a very basic implementation, replace this with the requests
    # module or something else when porting to Python 3. We can try to remove
    # our dependency on wget/curl.
    cerbero.utils.shell.download = cerbero.utils.shell.download_urllib2
