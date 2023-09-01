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
import pathlib


### XML Hacks ###

import re
import io
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
    tmpfile = io.BytesIO()
    oldwrite(self, tmpfile, encoding)
    tmpfile.seek(0)
    if hasattr(file_or_filename, "write"):
        out_file = file_or_filename
    else:
        out_file = open(file_or_filename, "wb")
    out_file.write(pretify(tmpfile.read()).encode())
    if not hasattr(file_or_filename, "write"):
        out_file.close()


etree.ElementTree.write = write


### Windows Hacks ###

# we don't want backlashes in paths as it breaks shell commands
oldjoin = os.path.join
oldexpanduser = os.path.expanduser
oldabspath = os.path.abspath
oldrealpath = os.path.realpath
oldrelpath = os.path.relpath


def join(*args):
    return pathlib.PurePath(oldjoin(*args)).as_posix()


def expanduser(path):
    return oldexpanduser(path).replace('\\', '/')


def abspath(path):
    return oldabspath(path).replace('\\', '/')


def realpath(path):
    return oldrealpath(path).replace('\\', '/')


def relpath(path, start=None):
    os.path.abspath = oldabspath
    ret = oldrelpath(path, start).replace('\\', '/')
    os.path.abspath = abspath
    return ret


if sys.platform.startswith('win'):
    # FIXME: replace all usage of os.path.join with pathlib.PurePath.as_posix()
    # instead of doing this brittle monkey-patching.
    os.path.join = join
    os.path.expanduser = expanduser
    os.path.abspath = abspath
    os.path.realpath = realpath
    os.path.relpath = relpath

    # On windows, python transforms all enviroment variables to uppercase,
    # but we need lowercase ones to override configure options like
    # am_cv_python_platform
    os.environ.encodekey = os.environ.encodevalue


import stat
import shutil
from shutil import rmtree as shutil_rmtree
from cerbero.utils.shell import new_call as shell_call

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


### Python ZipFile module bug ###
# zipfile.ZipFile.extractall() does not preserve permissions
# https://bugs.python.org/issue15795

import zipfile
from zipfile import ZipFile as zipfile_ZipFile

class ZipFile(zipfile_ZipFile):
    def _extract_member(self, member, targetpath, pwd):
        """Extract the ZipInfo object 'member' to a physical
           file on the path targetpath.
        """
        if not isinstance(member, zipfile.ZipInfo):
            member = self.getinfo(member)

        # build the destination pathname, replacing
        # forward slashes to platform specific separators.
        arcname = member.filename.replace('/', os.path.sep)

        if os.path.altsep:
            arcname = arcname.replace(os.path.altsep, os.path.sep)
        # interpret absolute pathname as relative, remove drive letter or
        # UNC path, redundant separators, "." and ".." components.
        arcname = os.path.splitdrive(arcname)[1]
        invalid_path_parts = ('', os.path.curdir, os.path.pardir)
        arcname = os.path.sep.join(x for x in arcname.split(os.path.sep)
                                   if x not in invalid_path_parts)
        if os.path.sep == '\\':
            # filter illegal characters on Windows
            arcname = self._sanitize_windows_name(arcname, os.path.sep)

        targetpath = os.path.join(targetpath, arcname)
        targetpath = os.path.normpath(targetpath)

        # Create all upper directories if necessary.
        upperdirs = os.path.dirname(targetpath)
        if upperdirs and not os.path.exists(upperdirs):
            os.makedirs(upperdirs)

        # Unlink before extracting, this ensures that if there is a symbolic
        # link in place it will not be followed to the (possibly non existing)
        # destination.
        try:
            os.unlink(targetpath)
        except (FileNotFoundError, IsADirectoryError):
            pass

        if member.is_dir():
            if not os.path.isdir(targetpath):
                os.mkdir(targetpath)
            return targetpath

        # Handle symlinks.
        if (member.external_attr >> 28) == 0xA:
            os.symlink(self.read(member), targetpath)
            return targetpath

        with self.open(member, pwd=pwd) as source, \
             open(targetpath, "wb") as target:
            shutil.copyfileobj(source, target)

        attr = member.external_attr >> 16
        if attr != 0:
            os.chmod(targetpath, attr)

        return targetpath

zipfile.ZipFile = ZipFile

### Python os.symlink bug ###
# os.symlink doesn't convert / to \ and writes out an invalid path entry
# instead. This breaks extracting of tarballs with symlinks, such as our mingw
# toolchain tarball.
# https://bugs.python.org/issue13702#msg218029

from pathlib import WindowsPath
from os import symlink as os_symlink

def symlink(src, dst, **kwargs):
    src = str(WindowsPath(src))
    os_symlink(src, dst, **kwargs)

if sys.platform.startswith('win'):
    os.symlink = symlink

### Python tarfile bug ###
# tarfile does not correctly handle the case when it needs to overwrite an
# existing symlink, since os.symlink returns FileExistsError (subclass of
# OSError) and tarfile.makelink() thinks it's a permissions issue (it checks
# for OSError). So we need to handle that too by checking whether `dst` is
# a symlink and deleting it in that case.

import tarfile

def symlink_overwrite(src, dst, **kwargs):
    # Allow overwriting symlinks
    try:
        if os.path.islink(dst):
            os.remove(dst)
    except OSError:
        pass
    symlink(src, dst, **kwargs)

if sys.platform.startswith('win'):
    tarfile.os.symlink = symlink_overwrite
