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

from cerbero.config import Platform
from cerbero.packages import package
from cerbero.packages.packagesstore import PackagesStore


class Package1(package.Package):

    name = 'gstreamer-test1'
    shortdesc = 'GStreamer Test'
    version = '1.0'
    licences = ['LGPL']
    uuid = '1'
    vendor = 'GStreamer Project'
    deps = ['gstreamer-test2']

    files = ['README', 'libexec/gstreamer-0.10/pluginsloader%(bext)s']
    platform_files = {
        Platform.WINDOWS: ['windows'],
        Platform.LINUX: ['linux']}

    binaries = ['gst-launch']
    platform_bins = {
        Platform.WINDOWS: ['windows'],
        Platform.LINUX: ['linux']}

    libraries = ['libgstreamer']
    platform_libs = {
        Platform.WINDOWS: ['libgstreamer-win32'],
        Platform.LINUX: ['libgstreamer-x11']}


class Package2(package.Package):

    name = 'gstreamer-test2'
    shortdesc = 'GStreamer Test 2'
    version = '1.0'
    licences = ['LGPL']
    uuid = '1'
    vendor = 'GStreamer Project'

    files = ['README2']


class Package3(package.Package):

    name = 'gstreamer-test3'
    shortdesc = 'GStreamer Test 3'
    version = '1.0'
    licences = ['LGPL']
    uuid = '1'
    vendor = 'GStreamer Project'

    files = ['README2']


class Package4(package.Package):

    name = 'gstreamer-test-bindings'
    shortdesc = 'GStreamer Bindings'
    version = '1.0'
    licences = ['LGPL']
    uuid = '1'
    vendor = 'GStreamer Project'

    files = ['README3']


class MetaPackage(package.MetaPackage):

    name = "gstreamer-runtime"
    shortdesc = "GStreamer runtime"
    longdesc = "GStreamer runtime"
    title = "GStreamer runtime"
    url = "http://www.gstreamer.net"
    version = '1.0'
    uuid = '3ffe67b2-4565-411f-8287-e8faa892f853'
    vendor = "GStreamer Project"
    org = 'net.gstreamer'
    packages = [
                ('gstreamer-test1', True, True),
                ('gstreamer-test3', False, True),
                ('gstreamer-test-bindings', False, False)]
    features = {'bindings': 'GStreamer Bindings'}
    icon = "gstreamer.ico"
    install_dir = {
        Platform.WINDOWS: 'GStreamer',
        Platform.LINUX: '/usr/local/gstreamer',
        Platform.DARWIN: 'GStreamer.framework'}


class DummyConfig(object):
    pass


def create_store(config):
    store = PackagesStore(object(), False)

    for klass in [Package1, Package2, Package3, Package4, MetaPackage]:
        package = klass(config)
        store.add_package(package)
    return store
