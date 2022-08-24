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

import logging

from cerbero.errors import FatalError
from cerbero.utils import _
from cerbero.utils import messages as m
from cerbero.bootstrap.build_tools import BuildTools
from cerbero.bootstrap.rust import RustBootstrapper


toolchain_bootstrappers = {}
system_bootstrappers = {}


def register_system_bootstrapper(distro, klass, distro_version=None):
    if not distro in system_bootstrappers:
        system_bootstrappers[distro] = {}
    system_bootstrappers[distro][distro_version] = klass

def register_toolchain_bootstrapper(distro, klass, distro_version=None):
    if not distro in toolchain_bootstrappers:
        toolchain_bootstrappers[distro] = {}
    toolchain_bootstrappers[distro][distro_version] = klass


class Bootstrapper (object):
    def __new__(klass, config, system, toolchains, build_tools, offline, assume_yes):
        bs = []

        target_distro = config.target_distro
        distro = config.distro
        target_distro_version = config.target_distro_version
        distro_version = config.distro_version

        # Try to find a bootstrapper for the distro-distro_version combination,
        # both for the target host and the build one. For instance, when
        # bootstraping to cross-compile for windows we also need to bootstrap
        # the build host.
        target = (target_distro, target_distro_version)
        build = (distro, distro_version)

        # Always run the system bootstrapper first (if enabled)
        if system:
            d, v = build
            if d not in system_bootstrappers:
                raise FatalError(_("No system bootstrapper for %s" % d))
            if v not in system_bootstrappers[d]:
                v = None
            bs.append(system_bootstrappers[d][v](config, offline, assume_yes))

        # We need to run the toolchain bootstrapper for the target, not the
        # build because we might be cross-compiling
        if toolchains:
            d, v = target
            # We don't require a toolchain bootstrapper when not
            # cross-compiling, and when cross-compiling we sometimes rely on
            # the system to provide it. For example, when cross-compiling to
            # Linux-ARM or to UWP.
            if d in toolchain_bootstrappers:
                if v not in toolchain_bootstrappers[d]:
                    v = None
                bs.append(toolchain_bootstrappers[d][v](config, offline, assume_yes))
            if config.variants.rust:
                bs.append(RustBootstrapper(config, offline))

        # Build the build-tools after all other bootstrappers
        if build_tools:
            bs.append(BuildTools(config, offline))

        return bs

from cerbero.bootstrap import linux, windows, android, osx, ios

linux.register_all()
windows.register_all()
android.register_all()
osx.register_all()
ios.register_all()
