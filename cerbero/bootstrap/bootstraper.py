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


bootstrapers = {}


def register_bootstraper(distro, klass, distro_version=None):
    if not distro in bootstrapers:
        bootstrapers[distro] = {}
    bootstrapers[distro][distro_version] = klass


class Bootstraper (object):
    def __new__(klass, config, build_tools_only):
        bs = []

        bs.append(BuildTools(config))
        if build_tools_only:
            return bs

        target_distro = config.target_distro
        distro = config.distro
        target_distro_version = config.target_distro_version
        distro_version = config.distro_version

        # Try to find a bootstraper for the distro-distro_version combination,
        # both for the target host and the build one. For instance, when
        # bootstraping to cross-compile for windows we also need to bootstrap
        # the build host.
        target = (target_distro, target_distro_version)
        build = (distro, distro_version)

        if target == build:
            blist = [target]
        else:
            blist = [target, build]

        for d, v in blist:
            if d not in bootstrapers:
                raise FatalError(_("No bootstrapper for the distro %s" % d))
            if v not in bootstrapers[d]:
                # Be tolerant with the distro version
                m.warning(_("No bootstrapper for the distro version %s" % v))
                v = None

            bs.insert(0, bootstrapers[d][v](config))

        return bs

from cerbero.bootstrap import linux, windows, android, osx, ios

linux.register_all()
windows.register_all()
android.register_all()
osx.register_all()
ios.register_all()
