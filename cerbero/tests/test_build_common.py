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

from cerbero.config import Platform
from cerbero.build.cookbook import CookBook
from cerbero.build import recipe
from cerbero.utils import shell


class Recipe1(recipe.Recipe):

    name = 'recipe1'
    licence = 'LGPL'
    uuid = '1'

    files_misc = ['README', 'libexec/gstreamer-0.10/pluginsloader%(bext)s']
    platform_files_misc = {
        Platform.WINDOWS: ['windows'],
        Platform.LINUX: ['linux']}

    files_bins = ['gst-launch']
    platform_files_bins = {
        Platform.WINDOWS: ['windows'],
        Platform.LINUX: ['linux']}

    files_libs = ['libgstreamer-0.10']
    platform_files_libs = {
        Platform.WINDOWS: ['libgstreamer-win32'],
        Platform.LINUX: ['libgstreamer-x11']}


class Recipe2(recipe.Recipe):

    name = 'recipe2'
    licence = 'GPL'

    files_misc = ['README2']


class Recipe3(recipe.Recipe):

    name = 'recipe3'
    licences = 'BSD'

    files_misc = ['README3']


class Recipe4(recipe.Recipe):

    name = 'recipe4'
    licence = 'LGPL'

    files_misc = ['README4']


class Recipe5(recipe.Recipe):

    name = 'recipe5'
    licence = 'LGPL'

    files_libs = ['libtest']


def add_files(tmp):
    bindir = os.path.join(tmp, 'bin')
    libdir = os.path.join(tmp, 'lib')
    os.path.join(tmp, 'include')
    os.makedirs(bindir)
    os.makedirs(libdir)
    shell.call('touch '
        '%(bindir)s/libgstreamer-0.10.dll '
        '%(bindir)s/libgstreamer-win32.dll '
        '%(bindir)s/libtest.dll '
        '%(libdir)s/libtest.so.1 '
        '%(libdir)s/libtest.la '
        '%(libdir)s/libtest.a '
        '%(libdir)s/libtest.so '
        '%(libdir)s/libtest.dll.a '
        '%(libdir)s/libgstreamer-0.10.so.1 '
        '%(libdir)s/libgstreamer-0.10.la '
        '%(libdir)s/libgstreamer-0.10.a '
        '%(libdir)s/libgstreamer-0.10.so '
        '%(libdir)s/libgstreamer-0.10.dll.a '
        '%(libdir)s/libgstreamer-win32.la '
        '%(libdir)s/libgstreamer-win32.a '
        '%(libdir)s/libgstreamer-win32.so '
        '%(libdir)s/libgstreamer-win32.dll.a '
        '%(libdir)s/libgstreamer-x11.so.1 '
        '%(libdir)s/libgstreamer-x11.so '
        '%(libdir)s/libgstreamer-x11.a '
        '%(libdir)s/libgstreamer-x11.la ' %
        {'bindir': bindir, 'libdir':libdir})


def create_cookbook(config):
    cb = CookBook(config, False)

    for klass in [Recipe1, Recipe2, Recipe3, Recipe4, Recipe5]:
        cb.add_recipe(klass(config))
    return cb
