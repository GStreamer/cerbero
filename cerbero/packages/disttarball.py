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
import shutil
import tempfile

import cerbero.utils.messages as m
from cerbero.utils import _
from cerbero.utils.tar import Tar
from cerbero.enums import Platform
from cerbero.errors import EmptyPackageError
from cerbero.packages import PackagerBase, PackageType
from cerbero.tools import strip


class DistTarball(PackagerBase):
    """Creates a distribution tarball"""

    def __init__(self, config, package, store):
        PackagerBase.__init__(self, config, package, store)
        self.package = package
        self.prefix = config.prefix
        self.package_prefix = ''
        if self.config.packages_prefix is not None:
            self.package_prefix = '%s-' % self.config.packages_prefix
        self.compress = config.package_tarball_compression

    def pack(
        self, output_dir, devel=True, force=False, keep_temp=False, split=True, package_prefix='', strip_binaries=False
    ):
        try:
            dist_files = self.files_list(PackageType.RUNTIME, force)
        except EmptyPackageError:
            m.warning(_('The runtime package is empty'))
            dist_files = []

        if devel:
            try:
                devel_files = self.files_list(PackageType.DEVEL, force)
            except EmptyPackageError:
                m.warning(_('The development package is empty'))
                devel_files = []
        else:
            devel_files = []

        if not split:
            dist_files += devel_files

        if not dist_files and not devel_files:
            raise EmptyPackageError(self.package.name)

        filenames = []
        if dist_files:
            if not strip_binaries:
                runtime = self._create_tarball(output_dir, PackageType.RUNTIME, dist_files, force, package_prefix)
            else:
                runtime = self._create_tarball_stripped(
                    output_dir, PackageType.RUNTIME, dist_files, force, package_prefix
                )
            filenames.append(runtime)

        if split and devel and len(devel_files) != 0:
            devel = self._create_tarball(output_dir, PackageType.DEVEL, devel_files, force, package_prefix)
            filenames.append(devel)
        return filenames

    def _get_ext(self, ext=None):
        if ext is not None:
            return ext
        if self.compress == 'none':
            return 'tar'
        return 'tar.' + self.compress

    def _get_name(self, package_type: PackageType, ext=None):
        ext = self._get_ext(ext)

        if self.config.target_platform != Platform.WINDOWS:
            platform = self.config.target_platform
        elif self.config.variants.uwp:
            platform = 'uwp'
        elif self.config.variants.visualstudio:
            platform = 'msvc'
        else:
            platform = 'mingw'

        if self.config.variants.visualstudio and self.config.variants.vscrt == 'mdd':
            platform += '+debug'

        return '%s%s-%s-%s-%s%s.%s' % (
            self.package_prefix,
            self.package.name,
            platform,
            self.config.target_arch,
            self.package.version,
            package_type,
            ext,
        )

    def _create_tarball_stripped(self, output_dir, package_type, files, force, package_prefix):
        tmpdir = tempfile.mkdtemp(dir=self.config.home_dir)

        if hasattr(self.package, 'strip_excludes'):
            s = strip.Strip(self.config, self.package.strip_excludes)
        else:
            s = strip.Strip(self.config)

        for f in files:
            orig_file = os.path.join(self.prefix, f)
            tmp_file = os.path.join(tmpdir, f)
            tmp_file_dir = os.path.dirname(tmp_file)
            if not os.path.exists(tmp_file_dir):
                os.makedirs(tmp_file_dir)
            shutil.copy(orig_file, tmp_file, follow_symlinks=False)
            s.strip_file(tmp_file)

        prefix_restore = self.prefix
        self.prefix = tmpdir
        tarball = self._create_tarball(output_dir, package_type, files, force, package_prefix)
        self.prefix = prefix_restore
        shutil.rmtree(tmpdir)

        return tarball

    def _create_tarball(self, output_dir, package_type, files, force, package_prefix):
        filename = os.path.join(output_dir, self._get_name(package_type))
        Tar(filename).configure(self.config, self.prefix).pack(files, package_prefix, force)
        return filename


class Packager(object):
    ARTIFACT_TYPE = 'tarball'

    def __new__(klass, config, package, store):
        return DistTarball(config, package, store)


def register():
    from cerbero.packages.packager import register_packager
    from cerbero.config import Distro

    register_packager(Distro.NONE, Packager)
    register_packager(Distro.GENTOO, Packager)
