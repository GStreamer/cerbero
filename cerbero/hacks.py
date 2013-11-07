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

# rmtree fails to often with access denied
import shutil
from cerbero.utils.shell import call


def rmtree(path, onerror=None):
    call('rm -rf %s' % path)


shutil.rmtree = rmtree



### OS X Hacks ###

# use cURL to download instead of wget

if sys.platform.startswith('darwin'):
    import cerbero.utils.shell as cshell
    del cshell.download
    cshell.download = cshell.download_curl
