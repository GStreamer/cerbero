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
import tarfile
import tempfile

import cerbero.utils.messages as m
from cerbero.utils import shell, _
from cerbero.enums import Platform, Distro
from cerbero.errors import FatalError, UsageError, EmptyPackageError
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
        if self.compress not in ('none', 'bz2', 'xz'):
            raise UsageError('Invalid compression type {!r}'.format(self.compress))

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

    def _get_name(self, package_type, ext=None):
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
        if os.path.exists(filename):
            if force:
                os.remove(filename)
            else:
                raise UsageError('File %s already exists' % filename)
        if self.config.distro == Distro.MSYS:
            self._write_tar_windows(filename, package_prefix, files)
        else:
            self._write_tar(filename, package_prefix, files)
        return filename

    def _compress_tar(self, tar_filename):
        if self.compress == 'bz2':
            compress_cmd = ['bzip2']
        elif self.compress == 'xz':
            compress_cmd = ['xz', '--verbose', '--threads', '0']
        compress_cmd += ['-z', '-f', tar_filename]
        shell.new_call(compress_cmd)

    def _write_tar_windows(self, filename, package_prefix, files):
        # MSYS tar is very old and creates broken archives, so we use Python's
        # tarfile module instead. However, tarfile's compression is very slow,
        # so we create an uncompressed tarball and then compress it using bzip2
        # or xz as appropriate.
        tar_filename = os.path.splitext(filename)[0]
        if os.path.exists(tar_filename):
            os.remove(tar_filename)
        try:
            with tarfile.open(tar_filename, 'w') as tar:
                for f in files:
                    filepath = os.path.join(self.prefix, f)
                    tar.add(filepath, os.path.join(package_prefix, f))
        except OSError:
            os.replace(tar_filename, tar_filename + '.partial')
            raise
        if self.compress == 'none':
            return
        # Compress the tarball
        self._compress_tar(tar_filename)

    def _write_tar(self, filename, package_prefix, files):
        tar = shell.get_tar_cmd()
        tar_cmd = [tar, '-C', self.prefix]
        # --checkpoint is only supported by GNU tar
        if tar == shell.HOMEBREW_TAR or (self.config.platform != Platform.DARWIN and tar == shell.TAR):
            tar_cmd.append('--checkpoint=.250')
        # ensure we provide a unique list of files to tar to avoid
        # it creating hard links/copies
        files = sorted(set(files))

        if package_prefix:
            # Only transform the files (and not symbolic/hard links)
            tar_cmd += ['--transform', 'flags=r;s|^|{}/|'.format(package_prefix)]
        if self.compress == 'bz2':
            # Use lbzip2 when available for parallel compression
            if shutil.which('lbzip2'):
                tar_cmd += ['--use-compress-program=lbzip2']
            else:
                tar_cmd += ['--bzip2']
        elif self.compress == 'xz':
            # bsdtar hangs when piping to an external compress-program, and
            # --xz is very slow because it doesn't use XZ_OPT (probably uses
            # libarchive) and single-threaded xz is 6-10x slower. So we create
            # a plain tar using bsdtar first, then compress it with xz later.
            filename = os.path.splitext(filename)[0]
        elif self.compress != 'none':
            raise AssertionError('Unknown tar compression: {}'.format(self.compress))

        tar_cmd += ['-cf', filename]
        with tempfile.TemporaryDirectory() as d:
            fname = os.path.join(d, 'cerbero_files_list')
            with open(fname, 'w', newline='\n', encoding='utf-8') as f:
                for line in files:
                    f.write(f'{line}\n')
            try:
                # Supply the files list using a file else the command can get
                # too long to invoke, especially on Windows.
                shell.new_call(tar_cmd + ['-T', fname])
            except FatalError:
                os.replace(filename, filename + '.partial')
                raise
        if self.compress == 'xz':
            # We didn't compress it with tar, compress it now
            self._compress_tar(filename)


class Packager(object):
    def __new__(klass, config, package, store):
        return DistTarball(config, package, store)


def register():
    from cerbero.packages.packager import register_packager
    from cerbero.config import Distro

    register_packager(Distro.NONE, Packager)
    register_packager(Distro.GENTOO, Packager)
