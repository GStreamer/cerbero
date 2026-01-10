from functools import lru_cache
import os
import tarfile
import tempfile
import shutil
import traceback

from cerbero.enums import Distro, Platform
from cerbero.errors import CommandError, UsageError, FatalError
from cerbero.utils import shell, to_unixpath
from cerbero.utils import messages as m


class Tar:
    class Compression:
        BZ2 = 'bz2'
        XZ = 'xz'
        TAR = 'tar'
        ZSTD = 'zst'

    STOCK_TAR = (None, 'tar')
    HOMEBREW_TAR = ('brew', 'gtar')
    # We cannot use this, it hangs when combined with xz from MSYS2. Added here
    # just for completeness.
    WIN32_BSD_TAR = ('win32', r'C:\Windows\System32\tar.exe')
    MSYS_BSD_TAR = ('msys', 'bsdtar')
    MSYS_GNU_TAR = ('msys', 'tar')
    TARBALL_SUFFIXES = ('tar.gz', 'tgz', 'tar.bz2', 'tbz2', 'tar.xz', 'tar.zst', 'tar.zstd')

    def __init__(self, filename):
        self.filename = str(filename)
        self.decompress_args = ['--no-same-owner', '-x']
        # Exclude symlinks on Windows
        if shell.PLATFORM == Platform.WINDOWS:
            self.decompress_args += [
                '--exclude=*.so',
                '--exclude=.gitlab-ci.d/meson-cross/*',
            ]

    def configure(self, config, files_prefix, compress=None):
        self.distro = config.distro
        self.platform = config.platform
        self.compress = compress
        if not self.compress:
            self.compress = config.package_tarball_compression
        if self.compress == 'none':
            self.compress = Tar.Compression.TAR
        if self.compress not in (Tar.Compression.TAR, Tar.Compression.BZ2, Tar.Compression.XZ, Tar.Compression.ZSTD):
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

    def unpack_params(self, output_dir, logfile=None):
        tar_cmd = self.get_cmd()
        tar_env = os.environ.copy()
        tar_args = []
        if self.filename.endswith('.xz'):
            if shutil.which('xz'):
                tar_args += ['--use-compress-program=xz -d -T0']
            else:
                if self.config.platform == Platform.DARWIN:
                    m.warning('Could not find `xz` for parallel lzma decompression with bsdtar')
                tar_env['XZ_OPT'] = '-T0'
        tar_args += ['-C', output_dir, '-f', str(self.filename)]
        return (tar_cmd, tar_args, tar_env)

    async def unpack_tarfile(self, output_dir):
        cmode = 'bz2' if self.filename.endswith('bz2') else self.filename[-2:]
        tf = tarfile.open(self.filename, mode='r:' + cmode)
        # Unfortunately this is not async, so it will block
        tf.extractall(path=output_dir)

    async def unpack(self, output_dir, logfile=None):
        if Tar.uses_ancient_msys_tar():
            # We can't use MSYS tar (not MSYS2) on Windows because it is
            # ancient and buggy.
            await self.unpack_tarfile(output_dir)
            return

        os.makedirs(output_dir, exist_ok=True)

        tar_cmd, tar_args, tar_env = self.unpack_params(output_dir, logfile)
        try:
            await shell.async_call(
                [tar_cmd[1]] + self.decompress_args + tar_args,
                env=tar_env,
                logfile=logfile,
            )
            return
        except CommandError:
            if logfile:
                traceback.print_exc(file=logfile)
                logfile.write('tar command {} failed, trying next'.format(tar_cmd[1]))

        if shell.PLATFORM == Platform.WINDOWS:
            if tar_cmd != self.MSYS_BSD_TAR:
                try:
                    await shell.async_call(
                        [self.MSYS_BSD_TAR[1], '-f', self.filename, '-C', output_dir] + self.decompress_args,
                        env=os.environ.copy(),
                        logfile=logfile,
                    )
                    return
                except CommandError:
                    if logfile:
                        traceback.print_exc(file=logfile)
                        logfile.write('MSYS2 bsdtar command failed, trying next')
            if tar_cmd != self.MSYS_GNU_TAR:
                try:
                    await shell.async_call(
                        [self.MSYS_GNU_TAR[1], '-f', to_unixpath(self.filename), '-C', to_unixpath(output_dir)]
                        + self.decompress_args,
                        env=os.environ.copy(),
                        logfile=logfile,
                    )
                    return
                except CommandError:
                    if logfile:
                        traceback.print_exc(file=logfile)
                        logfile.write('MSYS2 tar command failed, trying next')
        # Finally, try tarfile
        await self.unpack_tarfile(output_dir)

    def unpack_sync(self, output_dir):
        os.makedirs(output_dir, exist_ok=True)
        tar_cmd, tar_args, tar_env = self.unpack_params(output_dir, None)
        return shell.new_call([tar_cmd[1]] + self.decompress_args + tar_args)

    def _compress_tar(self, tar_filename):
        compress_cmd = None
        if self.compress == Tar.Compression.BZ2:
            compress_cmd = ['bzip2']
        elif self.compress == Tar.Compression.XZ:
            compress_cmd = ['xz', '--verbose', '--threads', '0']
        elif self.compress == Tar.Compression.ZSTD:
            # level 18 takes roughly as much (3m 20s) as XZ
            # to compress a whole Windows MinGW tarball pair
            # (Ryzen 7 2700x on Windows 10, NVMe drive)
            compress_cmd = ['zstd', '-T0', '-18']

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
        tar_cmd = [tar[1], '-C', self.prefix]
        # --checkpoint is only supported by GNU tar
        if tar == Tar.HOMEBREW_TAR or (self.platform != Platform.DARWIN and tar == Tar.STOCK_TAR):
            tar_cmd.append('--checkpoint=.250')
        # ensure we provide a unique list of files to tar to avoid
        # it creating hard links/copies
        files = sorted(set(files))
        tar_env = os.environ.copy()

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
            if Tar.uses_ancient_msys_tar():
                # bsdtar hangs when piping to an external compress-program, and
                # --xz is very slow because it doesn't use XZ_OPT (probably uses
                # libarchive) and single-threaded xz is 6-10x slower. So we create
                # a plain tar using bsdtar first, then compress it with xz later.
                tar_filename = os.path.splitext(tar_filename)[0]
            else:
                if shutil.which('xz'):
                    # Use xz when available for parallel compression. This is
                    # supported by both BSD tar and GNU tar.
                    tar_cmd += ['--use-compress-program=xz -T0']
                else:
                    # GNU tar and bsdtar's built-in xz support via liblzma
                    # doesn't use parallel compression. However, GNU tar will
                    # read XZ_OPT and do the right thing. Maybe some day so
                    # will BSD tar.
                    if self.config.platform == Platform.DARWIN:
                        m.warning('Could not find `xz` for parallel lzma compression with bsdtar')
                    tar_cmd += ['--xz']
                    tar_env['XZ_OPT'] = '-T0'
        elif self.compress == Tar.Compression.ZSTD:
            # zst is MSYS2's default compression algorithm
            if tar == Tar.MSYS_BSD_TAR:
                tar_cmd += ['--zstd', '--options', 'zstd:threads=0,zstd:compression-level=18']
            elif shutil.which('zstd'):
                tar_cmd += ['--use-compress-program=zstd -T0 -18']
            else:
                raise UsageError('zstd is not available in the PATH')

        tar_cmd += ['-cf', tar_filename]
        with tempfile.TemporaryDirectory() as d:
            fname = os.path.join(d, 'cerbero_files_list')
            with open(fname, 'w', newline='\n', encoding='utf-8') as f:
                for line in files:
                    f.write(f'{line}\n')
            try:
                # Supply the files list using a file else the command can get
                # too long to invoke, especially on Windows.
                shell.new_call(tar_cmd + ['-T', fname], env=tar_env)
            except FatalError:
                os.replace(tar_filename, tar_filename + '.partial')
                raise
        if self.compress == Tar.Compression.XZ and Tar.uses_ancient_msys_tar():
            # We didn't compress it with tar, compress it now
            self._compress_tar(tar_filename)

    @staticmethod
    @lru_cache()
    def get_cmd():
        # Try various BSD tars first on Windows, since they seem to have better perf
        if shell.PLATFORM == Platform.WINDOWS:
            if shell.DISTRO == Distro.MSYS2:
                return Tar.MSYS_BSD_TAR
            return Tar.MSYS_GNU_TAR
        # Allow using Homebrewed tar since it's GNU compatible
        # (macOS uses FreeBSD tar)
        if shell.PLATFORM == Platform.DARWIN:
            if shutil.which(Tar.HOMEBREW_TAR[1]):
                return Tar.HOMEBREW_TAR
        return Tar.STOCK_TAR
