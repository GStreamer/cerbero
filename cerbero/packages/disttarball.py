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

from cerbero.errors import UsageError
from cerbero.packages import PackagerBase, PackageType


class DistTarball(PackagerBase):
    ''' Creates a distribution tarball '''

    def __init__(self, config, package, store):
        PackagerBase.__init__(self, config, package, store)
        self.package = package
        self.prefix = config.prefix

    def pack(self, output_dir, devel=True, force=False, split=True,
             package_prefix=''):
        dist_files =  self.files_list(PackageType.RUNTIME, force)
        if devel:
            devel_files = self.files_list(PackageType.DEVEL, force)
        else:
            devel_files = []

        if not split:
            dist_files += devel_files

        filenames = []
        runtime = self._create_tarball(output_dir, PackageType.RUNTIME,
                                       dist_files, force, package_prefix)
        filenames.append(runtime)

        if split and devel:
            devel = self._create_tarball(output_dir, PackageType.DEVEL,
                                         devel_files, force, package_prefix)
            filenames.append(devel)
        return filenames

    def _get_name(self, package_type):
        return "%s-%s%s.tar.bz2" % (self.package.name, self.package.version,
                                    package_type)

    def _create_tarball(self, output_dir, package_type, files, force,
                        package_prefix):
        filename = os.path.join(output_dir, self._get_name(package_type))
        if os.path.exists(filename):
            if force:
                os.remove(filename)
            else:
                raise UsageError("File %s already exists" % filename)

        tar = tarfile.open(filename, "w:bz2")

        for f in files:
            filepath = os.path.join(self.prefix, f)
            tar.add(filepath, os.path.join(package_prefix, f))
        tar.close()

        return filename
