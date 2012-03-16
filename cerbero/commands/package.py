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

from cerbero.commands import Command, register_command
from cerbero.utils import _, N_, ArgparseArgument
from cerbero.utils import messages as m
from cerbero.errors import PackageNotFoundError
from cerbero.packages.packagesstore import PackagesStore
from cerbero.packages.disttarball import DistTarball


class Package(Command):
    doc = N_('Creates a distribution package')
    name = 'package'

    def __init__(self):
        Command.__init__(self,
            [ArgparseArgument('package', nargs=1,
                             help=_('name of the package to create')),
            ArgparseArgument('-o', '--output-dir', action='store_true', default=False,
                             help=_('Output directory for the tarball file')),
            ArgparseArgument('-t', '--tarball', action='store_true', default=False,
                             help=_('Creates a tarball instead of a native '
                                    'package')),
            ArgparseArgument('-f', '--force', action='store_true', default=False,
                             help=_('Delete any existing package file')),
            ])

    def run(self, config, args):
        store = PackagesStore(config)
        p = store.get_package(args.package[0])
        if p is None:
            raise PackageNotFoundError(args.package[0])
        if args.tarball:
            pkg = DistTarball(p)
        else:
            raise NotImplemented()
        m.action(_("Creating package for %s") % p.name)
        path = pkg.pack(args.output_dir, args.force)
        m.action(_("Package successfully created in %s") % path)


register_command(Package)
