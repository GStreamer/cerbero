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


def register_packager(distro, klass):
    if distro not in _packagers:
        _packagers[distro] = []
    _packagers[distro].append(klass)


class Packager(object):
    def __new__(cls, config, package, store, artifact_type=None):
        td = config.target_distro

        if td not in _packagers:
            raise FatalError(_('No packager available for the distro %s' % td))

        if td == Distro.DEBIAN:
            m.warning(
                'Creation of Debian packages is currently broken, please see '
                'https://gitlab.freedesktop.org/gstreamer/cerbero/issues/56\n'
                'Creating tarballs instead...'
            )
            td = Distro.NONE

        if td == Distro.WINDOWS and config.cross_compiling() and artifact_type in ('default', 'msi'):
            try:
                get_wix_prefix(config)
            except Exception:
                m.warning('Cross-compiling for Windows and WIX not found, building tarballs')
                td = Distro.NONE

        # Return the first packager that matches the artifact type
        if artifact_type:
            for p in _packagers[td]:
                if p.ARTIFACT_TYPE == artifact_type:
                    return p(config, package, store)
            raise FatalError(f'No {artifact_type} packager available for the distro {td}')

        # Return the first packager
        for p in _packagers[td]:
            return p(config, package, store)
        raise FatalError(f'No packager available for the distro {td}')


from cerbero.packages import rpm, debian, android, disttarball  # noqa: E402
from cerbero.packages.windows import inno_setup, wix_on_ninja  # noqa: E402
from cerbero.packages.osx import packager as osx_packager  # noqa: E402
from cerbero.packages.wheel import packager as wheel  # noqa: E402

osx_packager.register()
rpm.register()
debian.register()
android.register()
inno_setup.register()
wix_on_ninja.register()
disttarball.register()
wheel.register()
