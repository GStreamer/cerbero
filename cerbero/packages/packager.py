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

from cerbero.config import Distro
from cerbero.errors import FatalError
from cerbero.utils import _, get_wix_prefix
from cerbero.utils import messages as m


_packagers = {}


def register_packager(distro, klass, distro_version=None):
    if distro not in _packagers:
        _packagers[distro] = {}
    if distro_version not in _packagers[distro]:
        _packagers[distro][distro_version] = []
    _packagers[distro][distro_version].append(klass)


class Packager(object):
    def __new__(klass, config, package, store, artifact_type=None):
        d = config.target_distro
        v = config.target_distro_version

        if d not in _packagers:
            raise FatalError(_('No packager available for the distro %s' % d))

        if v not in _packagers[d]:
            # Be tolerant with the distro version
            m.warning(
                _(
                    'No specific packager available for the distro '
                    'version %s, using generic packager for distro %s' % (v, d)
                )
            )
            v = None

        if d == Distro.DEBIAN:
            m.warning(
                'Creation of Debian packages is currently broken, please see '
                'https://gitlab.freedesktop.org/gstreamer/cerbero/issues/56\n'
                'Creating tarballs instead...'
            )
            d = Distro.NONE
            v = None

        if d == Distro.WINDOWS and config.cross_compiling() and artifact_type in ('default', 'msi'):
            try:
                get_wix_prefix(config)
            except Exception:
                m.warning('Cross-compiling for Windows and WIX not found, overriding Packager')
                d = Distro.NONE

        if artifact_type:
            for p in _packagers[d][v]:
                if p.ARTIFACT_TYPE == artifact_type:
                    return p(config, package, store)
            raise FatalError('No %s packager available for the distro %s %s' % (artifact_type, d, v))
        else:
            # Assume first is the default
            return _packagers[d][v][0](config, package, store)


from cerbero.packages import rpm, debian, android, disttarball  # noqa: E402
from cerbero.packages.windows import wix_on_ninja  # noqa: E402
from cerbero.packages.osx import packager as osx_packager  # noqa: E402
from cerbero.packages.wheel import packager as wheel  # noqa: E402

wix_on_ninja.register()
osx_packager.register()
rpm.register()
debian.register()
android.register()
disttarball.register()
wheel.register()
