# cerbero - a multi-platform build system for Open Source software
# SPDX-FileCopyrightText: 2024 L. E. Segovia <amy@centricular.com>
# SPDX-License-Ref: LGPL-2.1-or-later

from pathlib import Path
import shutil
import tempfile

from cerbero.commands import Command, register_command
from cerbero.errors import PackageNotFoundError, UsageError
from cerbero.packages.packagesstore import PackagesStore
from cerbero.utils import shell
from cerbero.utils import _, N_, ArgparseArgument
from cerbero.utils import messages as m
from cerbero.utils.tar import Tar


class XCFramework(Command):
    doc = N_('Creates an Apple multiplatform binary framework bundle')
    name = 'xcframework'
    tmpdir_prefix = 'tarball-'

    def __init__(self):
        Command.__init__(
            self,
            [
                ArgparseArgument('package', nargs=1, help=_('name of the package to create')),
                ArgparseArgument('-o', '--output-dir', default='.', help=_('Output directory for the tarball file')),
                ArgparseArgument(
                    '-t',
                    '--tarball',
                    action='store_true',
                    default=False,
                    help=_('Creates a tarball instead of a native package'),
                ),
                ArgparseArgument(
                    '--source',
                    '-s',
                    action='append',
                    type=Path,
                    default=None,
                    help=_('Framework tarballs to combine into a single xcframework'),
                ),
                ArgparseArgument(
                    '-f', '--force', action='store_true', default=False, help=_('Delete any existing package file')
                ),
                ArgparseArgument(
                    '-k', '--keep-temp', action='store_true', default=False, help=_('Keep temporary files for debug')
                ),
                ArgparseArgument(
                    '--compress-method',
                    type=str,
                    choices=['default', 'xz', 'bz2', 'none'],
                    default='default',
                    help=_('Select compression method for tarballs'),
                ),
            ],
        )

    def list_fw_files(self, path):
        file_list = set()
        for f in Path(path).glob('**/*'):
            if not f.is_file():
                continue
            if f in ('Distribution.xml', '.gitignore'):
                continue
            f = str(f.relative_to(path))
            if f.startswith(self.tmpdir_prefix):
                continue
            file_list.add(f)
        return file_list

    def run(self, config, args):
        self.store = PackagesStore(config, offline=False)
        p = self.store.get_package(args.package[0])

        if args.compress_method != 'default':
            m.message('Forcing tarball compression method as ' + args.compress_method)
            config.package_tarball_compression = args.compress_method

        if p is None:
            raise PackageNotFoundError(args.package[0])

        m.action(_('Creating package for %s') % p.name)
        output_dir = Path(args.output_dir).absolute()

        dst = Path(output_dir) / 'gstreamer-xcframework.tar.xz'

        tmp = Path(tempfile.mkdtemp(prefix='xcframework-', dir=output_dir))
        xcfw = tmp / 'GStreamer.xcframework'
        xcodebuild = [shutil.which('xcodebuild'), '-create-xcframework']

        for tarball in args.source:
            tarball_folder = tempfile.mkdtemp(prefix=self.tmpdir_prefix, dir=tmp)
            m.action(f'Unpacking {tarball.name}')
            tarfile = Tar(tarball)
            tarfile.unpack_sync(tarball_folder)
            version_path = Path(tarball_folder) / 'GStreamer.framework' / 'Versions' / '1.0'
            library = version_path / 'lib' / 'libGStreamer.a'
            headers = version_path / 'Headers'
            if not library.exists():
                raise UsageError(f'Missing library libGStreamer.a in {tarball.name}')
            if not headers.exists():
                raise UsageError(f'Missing Headers folder in {tarball.name}')
            if library.is_symlink():
                real_lib = library.resolve(strict=True)
                library.unlink()
                shutil.copyfile(real_lib, library, follow_symlinks=True)
            xcodebuild += ['-library', library, '-headers', headers.absolute()]
        xcodebuild += ['-output', xcfw]
        shell.new_call(xcodebuild, cmd_dir=tmp)

        Tar(dst).configure(config, tmp).pack(self.list_fw_files(tmp), force=args.force)

        if args.keep_temp:
            m.action(f'Temporary build directory is at {tmp}')
        else:
            shutil.rmtree(tmp)
        m.action(_('Package successfully created in %s') % dst)


register_command(XCFramework)
