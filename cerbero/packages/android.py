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
import tarfile

from cerbero.config import Architecture
from cerbero.packages import PackageType, PackagerBase
from cerbero.packages.disttarball import DistTarball
from cerbero.errors import UsageError


class AndroidPackager(DistTarball):
    ''' Creates a distribution tarball for Android '''

    def _create_tarball(self, output_dir, package_type, files, force,
                        package_prefix):
        # Filter out some unwanted directories for the development package
        if package_type == PackageType.DEVEL:
            for filt in ['bin/', 'share/aclocal']:
                files = [x for x in files if not x.startswith(filt)]
        return super()._create_tarball(output_dir, package_type, files, force, package_prefix)

    def _get_name(self, package_type, ext=None):
        ext = self._get_ext(ext)

        if package_type == PackageType.DEVEL:
            package_type = ''
        elif package_type == PackageType.RUNTIME:
            package_type = '-runtime'

        return "%s%s-%s-%s-%s%s.%s" % (self.package_prefix, self.package.name,
                self.config.target_platform, self.config.target_arch,
                self.package.version, package_type, ext)


def register():
    from cerbero.packages.packager import register_packager
    from cerbero.config import Distro
    register_packager(Distro.ANDROID, AndroidPackager)
