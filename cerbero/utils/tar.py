from functools import lru_cache
import os
import tarfile
import tempfile
import shutil

from cerbero.enums import Distro, Platform
from cerbero.errors import UsageError, FatalError
from cerbero.utils import shell


class Tar:
    class Compression:
        BZ2 = 'bz2'
        XZ = 'xz'
        TAR = 'tar'

    STOCK_TAR = 'tar'
    HOMEBREW_TAR = 'gtar'
    MSYS_BSD_TAR = 'bsdtar'
    TARBALL_SUFFIXES = ('tar.gz', 'tgz', 'tar.bz2', 'tbz2', 'tar.xz')

    def __init__(self, filename):
        self.filename = filename

    def configure(self, config, files_prefix, compress=None):
        self.distro = config.distro
        self.platform = config.platform
        self.compress = compress
        if not self.compress:
            self.compress = config.package_tarball_compression
        if self.compress not in (Tar.Compression.TAR, Tar.Compression.BZ2, Tar.Compression.XZ):
            raise UsageError('Invalid compression type {!r}'.format(self.compress))
        self.prefix = files_prefix
        return self

    def pack(self, files, package_prefix='', force=False):
        if os.path.exists(self.filename):
            if force:
                os.remove(self.filename)
            else:
                raise UsageError('File %s already exists' % self.filename)
        if Tar.uses_ancient_msys_tar():
            self._write_tar_windows(package_prefix, files)
        else:
            self._write_tar(package_prefix, files)

    @staticmethod
    @lru_cache()
    def uses_ancient_msys_tar():
        return shell.DISTRO == Distro.MSYS and Tar.get_cmd() == Tar.STOCK_TAR

    async def unpack(self, output_dir, force_tarfile=False):
        # Recent versions of tar are much faster than the tarfile module, but we
        # can't use tar on Windows because MSYS tar is ancient and buggy.
        if Tar.uses_ancient_msys_tar() or force_tarfile:
            cmode = 'bz2' if self.filename.endswith('bz2') else self.filename[-2:]
            tf = tarfile.open(self.filename, mode='r:' + cmode)
            tf.extractall(path=output_dir)
        else:
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            await shell.async_call([self.get_cmd(), '-C', output_dir, '-xf', self.filename, '--no-same-owner'])

    def unpack_sync(self, output_dir):
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        return shell.new_call([self.get_cmd(), '-C', output_dir, '-xf', self.filename, '--no-same-owner'])

    def _compress_tar(self, tar_filename):
        compress_cmd = None
        if self.compress == Tar.Compression.BZ2:
            compress_cmd = ['bzip2']
        elif self.compress == Tar.Compression.XZ:
            compress_cmd = ['xz', '--verbose', '--threads', '0']

        if not compress_cmd:
            raise RuntimeError('Unspecified compression algorithm')
        compress_cmd += ['-z', '-f', tar_filename]
        shell.new_call(compress_cmd)

    def _write_tar_windows(self, package_prefix, files):
        # MSYS tar is very old and creates broken archives, so we use Python's
        # tarfile module instead. However, tarfile's compression is very slow,
        # so we create an uncompressed tarball and then compress it using bzip2
        # or xz as appropriate.
        tar_filename = os.path.splitext(self.filename)[0]
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
        if self.compress == Tar.Compression.TAR:
            return
        # Compress the tarball
        self._compress_tar(tar_filename)

    def _write_tar(self, package_prefix, files):
        tar_filename = self.filename
        tar = self.get_cmd()
        tar_cmd = [tar, '-C', self.prefix]
        # --checkpoint is only supported by GNU tar
        if tar == Tar.HOMEBREW_TAR or (self.platform != Platform.DARWIN and tar == Tar.STOCK_TAR):
            tar_cmd.append('--checkpoint=.250')
        # ensure we provide a unique list of files to tar to avoid
        # it creating hard links/copies
        files = sorted(set(files))

        if package_prefix:
            if self.platform == Platform.DARWIN and tar == Tar.STOCK_TAR:
                # bsdtar doesn't tolerate --transform, abort
                raise UsageError("Apple bsdtar doesn't support --transform")
            # Only transform the files (and not symbolic/hard links)
            tar_cmd += ['--transform', 'flags=r;s|^|{}/|'.format(package_prefix)]
        if self.compress == Tar.Compression.BZ2:
            # Use lbzip2 when available for parallel compression
            if shutil.which('lbzip2'):
                tar_cmd += ['--use-compress-program=lbzip2']
            else:
                tar_cmd += ['--bzip2']
        elif self.compress == Tar.Compression.XZ:
            if self.platform == Platform.DARWIN and tar == Tar.STOCK_TAR:
                # libarchive supports parallelism
                tar_cmd += ['--xz', '--options', 'xz:threads=0']
            elif self.platform == Platform.WINDOWS and tar == Tar.MSYS_BSD_TAR:
                # libarchive supports parallelism
                tar_cmd += ['--xz', '--options', 'xz:threads=0']
            elif Tar.uses_ancient_msys_tar():
                # bsdtar hangs when piping to an external compress-program, and
                # --xz is very slow because it doesn't use XZ_OPT (probably uses
                # libarchive) and single-threaded xz is 6-10x slower. So we create
                # a plain tar using bsdtar first, then compress it with xz later.
                tar_filename = os.path.splitext(tar_filename)[0]
            else:
                if shutil.which('xz'):
                    # Use xz when available for parallel compression
                    tar_cmd += ['--use-compress-program=xz -T0']
                else:
                    tar_cmd += ['--xz']

        tar_cmd += ['-cf', tar_filename]
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
                os.replace(tar_filename, tar_filename + '.partial')
                raise
        if self.compress == Tar.Compression.XZ and Tar.uses_ancient_msys_tar():
            # We didn't compress it with tar, compress it now
            self._compress_tar(tar_filename)

    @staticmethod
    @lru_cache()
    def get_cmd():
        """
        Returns the tar command to use

        @return: the tar command
        @rtype: str
        """
        # Use bsdtar with MSYS2 since tar hangs
        # https://github.com/msys2/MSYS2-packages/issues/1548
        if shell.DISTRO == Distro.MSYS2:
            return Tar.MSYS_BSD_TAR
        # Allow using Homebrewed tar since it's GNU compatible
        # (macOS uses FreeBSD tar)
        elif shutil.which(Tar.HOMEBREW_TAR):
            return Tar.HOMEBREW_TAR
        else:
            return Tar.STOCK_TAR
