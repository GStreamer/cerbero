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

from cerbero.config import Platform, Distro, DistroVersion
from cerbero.packages import package
from cerbero.packages.packagesstore import PackagesStore
from test.test_build_common import create_cookbook


class Package1(package.Package):
    name = 'gstreamer-test1'
    shortdesc = 'GStreamer Test'
    version = '1.0'
    licences = ['LGPL']
    uuid = '1'
    vendor = 'GStreamer Project'
    deps = ['gstreamer-test2']

    files = ['recipe1:misc:libs:bins']
    platform_files = {Platform.WINDOWS: ['recipe5:libs']}


class Package2(package.Package):
    name = 'gstreamer-test2'
    shortdesc = 'GStreamer Test 2'
    version = '1.0'
    licences = ['LGPL']
    uuid = '1'
    vendor = 'GStreamer Project'

    files = ['recipe2:misc']


class Package3(package.Package):
    name = 'gstreamer-test3'
    shortdesc = 'GStreamer Test 3'
    version = '1.0'
    licences = ['LGPL']
    uuid = '1'
    vendor = 'GStreamer Project'

    files = ['recipe3:misc']


class Package4(package.Package):
    name = 'gstreamer-test-bindings'
    shortdesc = 'GStreamer Bindings'
    version = '1.0'
    licences = ['LGPL']
    uuid = '1'
    vendor = 'GStreamer Project'
    sys_deps = {Distro.DEBIAN: ['python'], DistroVersion.FEDORA_16: ['python27']}

    files = ['recipe4:misc']


class MetaPackage(package.MetaPackage):
    name = 'gstreamer-runtime'
    shortdesc = 'GStreamer runtime'
    longdesc = 'GStreamer runtime'
    title = 'GStreamer runtime'
    url = 'http://www.gstreamer.net'
    version = '1.0'
    uuid = '3ffe67b2-4565-411f-8287-e8faa892f853'
    vendor = 'GStreamer Project'
    org = 'net.gstreamer'
    packages = [
        ('gstreamer-test1', True, True),
        ('gstreamer-test3', False, True),
        ('gstreamer-test-bindings', False, False),
    ]
    platform_packages = {Platform.LINUX: [('gstreamer-test2', False, False)]}
    icon = 'gstreamer.ico'


class App(package.App):
    name = 'gstreamer-app'
    shortdesc = 'GStreamer sample app'
    longdesc = 'GStreamer sample app'
    title = 'GStreamer sample app'
    url = 'http://www.gstreamer.net'
    version = '1.0'
    uuid = '3ffe67b2-4565-411f-8287-e8faa892f853'
    vendor = 'GStreamer Project'
    org = 'net.gstreamer'
    app_recipe = 'recipe3'
    deps = ['gstreamer-test1']
    icon = 'share/images/gstreamer.png'
    embed_deps = True


def create_store(config):
    cookbook = create_cookbook(config)
    store = PackagesStore(config, False)

    for klass in [Package1, Package2, Package3, Package4, App]:
        package = klass(config, store, cookbook)
        package.__file__ = 'test/test_packages_common.py'
        package.load()
        store.add_package(package)
    for klass in [MetaPackage]:
        package = klass(config, store)
        package.__file__ = 'test/test_packages_common.py'
        package.load()
        store.add_package(package)
    return store
