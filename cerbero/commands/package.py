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

from cerbero.config import Platform, Architecture
from cerbero.commands import Command, register_command, build
from cerbero.utils import _, N_, ArgparseArgument
from cerbero.utils import messages as m
from cerbero.errors import PackageNotFoundError, UsageError
from cerbero.packages.packager import Packager
from cerbero.packages.packagesstore import PackagesStore
from cerbero.packages.disttarball import DistTarball
from cerbero.packages.android import AndroidPackager


class Package(Command):
    doc = N_('Creates a distribution package')
    name = 'package'

    def __init__(self):
        Command.__init__(self,
            [ArgparseArgument('package', nargs=1,
                             help=_('name of the package to create')),
            ArgparseArgument('-o', '--output-dir', default='.',
                             help=_('Output directory for the tarball file')),
            ArgparseArgument('-t', '--tarball', action='store_true',
                default=False,
                help=_('Creates a tarball instead of a native package')),
            ArgparseArgument('-n', '--no-split', action='store_true',
                default=False,
                help=_('(only meaningfull when --tarball is set) Create one single '
                       'tarball with devel and runtime files')),
            ArgparseArgument('-f', '--force', action='store_true',
                default=False, help=_('Delete any existing package file')),
            ArgparseArgument('-d', '--no-devel', action='store_false',
                default=True, help=_('Do not create the development version '
                    'of this package')),
            ArgparseArgument('-s', '--skip-deps-build', action='store_true',
                default=False, help=_('Do not build the recipes needed to '
                    'create this package (conflicts with --only-build-deps)')),
            ArgparseArgument('-b', '--only-build-deps', action='store_true',
                default=False, help=_('Only build the recipes needed to '
                    'create this package (conflicts with --skip-deps-build)')),
            ArgparseArgument('-k', '--keep-temp', action='store_true',
                default=False, help=_('Keep temporary files for debug')),
            ArgparseArgument('--offline', action='store_true',
                default=False, help=_('Use only the source cache, no network')),
            ArgparseArgument('--dry-run', action='store_true',
                default=False, help=_('Only print the packages that will be built')),
            ArgparseArgument('--xz', action='store_true',
                default=False, help=_('Use xz instead of bzip2 for compression if '
                    'creating a tarball')),
            ArgparseArgument('--jobs', '-j', action='store', type=int,
                default=0, help=_('How many recipes to build concurrently. '
                    '0 = number of CPUs.')),
            ])

    def run(self, config, args):
        self.store = PackagesStore(config, offline=args.offline)
        p = self.store.get_package(args.package[0])

        if args.skip_deps_build and args.only_build_deps:
            raise UsageError(_("Cannot use --skip-deps-build together with "
                    "--only-build-deps"))

        if not args.skip_deps_build:
            self._build_deps(config, p, args.no_devel, args.offline, args.dry_run, args.jobs)

        if args.only_build_deps or args.dry_run:
            return

        if args.xz:
            config.package_tarball_compression = 'xz'

        if p is None:
            raise PackageNotFoundError(args.package[0])
        p.pre_package()
        if args.tarball:
            if config.target_platform == Platform.ANDROID and \
               config.target_arch == Architecture.UNIVERSAL:
                pkg = AndroidPackager(config, p, self.store)
            else:
                pkg = DistTarball(config, p, self.store)
        else:
            pkg = Packager(config, p, self.store)
        m.action(_("Creating package for %s") % p.name)
        output_dir = os.path.abspath(args.output_dir)
        if args.tarball:
            paths = pkg.pack(output_dir, args.no_devel, args.force,
                             args.keep_temp, split=not args.no_split,
                             strip_binaries=p.strip)
        else:
            paths = pkg.pack(output_dir, args.no_devel,
                             args.force, args.keep_temp)
        if None in paths:
            paths.remove(None)
        paths = p.post_package(paths, output_dir) or paths
        m.action(_("Package successfully created in %s") %
                 ' '.join([os.path.abspath(x) for x in paths]))

    def _build_deps(self, config, package, has_devel, offline, dry_run, jobs):
        build_command = build.Build()
        build_command.runargs(config, package.recipes_dependencies(has_devel),
            cookbook=self.store.cookbook, dry_run=dry_run, offline=offline,
            jobs=jobs)


register_command(Package)
