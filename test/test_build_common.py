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


# We create a common Recipe to make the MetaRecipe do its magic
# for recipes not named Recipe, like Recipe1
class Recipe(recipe.Recipe):
    pass


class Recipe1(Recipe):
    name = 'recipe1'
    version = '0.0.1'
    licence = 'LGPL'
    uuid = '1'

    files_misc = ['README', 'libexec/gstreamer-0.10/pluginsloader%(bext)s']
    platform_files_misc = {Platform.WINDOWS: ['windows'], Platform.LINUX: ['linux']}

    files_bins = ['gst-launch']
    platform_files_bins = {Platform.WINDOWS: ['windows'], Platform.LINUX: ['linux']}

    files_libs = ['libgstreamer-0.10']
    platform_files_libs = {Platform.WINDOWS: ['libgstreamer-win32'], Platform.LINUX: ['libgstreamer-x11']}


class Recipe2(Recipe):
    name = 'recipe2'
    version = '0.0.1'
    licence = 'GPL'

    files_misc = ['README2']


class Recipe3(Recipe):
    name = 'recipe3'
    version = '0.0.1'
    licences = 'BSD'

    files_misc = ['README3']


class Recipe4(Recipe):
    name = 'recipe4'
    version = '0.0.1'
    licence = 'LGPL'

    files_misc = ['README4']


class Recipe5(Recipe):
    name = 'recipe5'
    version = '0.0.1'
    licence = 'LGPL'

    files_libs = ['libtest']


def add_files(tmp):
    bindir = os.path.join(tmp, 'bin')
    libdir = os.path.join(tmp, 'lib', 'x86_64-linux-gnu')
    gstlibdir = os.path.join(tmp, 'libexec', 'gstreamer-0.10')
    os.makedirs(bindir)
    os.makedirs(libdir)
    os.makedirs(gstlibdir)
    shell.call(
        'touch '
        'windows '
        'linux '
        'README '
        'README2 '
        'README3 '
        'README4 '
        'README5 '
        'bin/gst-launch.exe '
        'bin/gst-launch '
        'bin/windows.exe '
        'bin/linux '
        'bin/libgstreamer-0.10.dll '
        'bin/libgstreamer-win32.dll '
        'bin/libtest.dll '
        'lib/x86_64-linux-gnu/libtest.so.1 '
        'lib/x86_64-linux-gnu/libtest.la '
        'lib/x86_64-linux-gnu/libtest.a '
        'lib/x86_64-linux-gnu/libtest.so '
        'lib/x86_64-linux-gnu/libtest.dll.a '
        'lib/x86_64-linux-gnu/libtest.def '
        'lib/x86_64-linux-gnu/test.lib '
        'lib/x86_64-linux-gnu/libgstreamer-0.10.so.1 '
        'lib/x86_64-linux-gnu/libgstreamer-0.10.la '
        'lib/x86_64-linux-gnu/libgstreamer-0.10.a '
        'lib/x86_64-linux-gnu/libgstreamer-0.10.so '
        'lib/x86_64-linux-gnu/libgstreamer-0.10.dll.a '
        'lib/x86_64-linux-gnu/gstreamer-0.10.lib '
        'lib/x86_64-linux-gnu/libgstreamer-0.10.def '
        'lib/x86_64-linux-gnu/libgstreamer-win32.la '
        'lib/x86_64-linux-gnu/libgstreamer-win32.a '
        'lib/x86_64-linux-gnu/libgstreamer-win32.so '
        'lib/x86_64-linux-gnu/libgstreamer-win32.dll.a '
        'lib/x86_64-linux-gnu/gstreamer-win32.lib '
        'lib/x86_64-linux-gnu/libgstreamer-win32.def '
        'lib/x86_64-linux-gnu/libgstreamer-x11.so.1 '
        'lib/x86_64-linux-gnu/libgstreamer-x11.so '
        'lib/x86_64-linux-gnu/libgstreamer-x11.a '
        'lib/x86_64-linux-gnu/libgstreamer-x11.la '
        'libexec/gstreamer-0.10/pluginsloader '
        'libexec/gstreamer-0.10/pluginsloader.exe ',
        tmp,
    )


def create_cookbook(config):
    cb = CookBook(config, False)

    for klass in [Recipe1, Recipe2, Recipe3, Recipe4, Recipe5]:
        r = klass(config, {})
        r.__file__ = 'test/test_build_common.py'
        cb.add_recipe(r)
    return cb
