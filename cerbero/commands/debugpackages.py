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

import collections
import itertools

from cerbero.commands import Command, register_command
from cerbero.utils import _, N_, ArgparseArgument, shell
from cerbero.utils import messages as m
from cerbero.packages.packagesstore import PackagesStore
from cerbero.packages.package import Package


class DebugPackages(Command):
    doc = N_('Outputs debug information about package, like duplicates files '
             'or files that do not belong to any package')
    name = 'debug-packages'

    def __init__(self):
        Command.__init__(self, [
            ArgparseArgument('-e', '--exclude',  nargs='*', default=[],
                help=_('Filter pattern to exclude files from the search')),
            ])

    def run(self, config, args):
        store = PackagesStore(config)

        allfiles = [p.all_files_list() for p in store.get_packages_list() if\
                    isinstance(p, Package)]
        allfiles = list(itertools.chain(*allfiles))

        self.find_duplicates(allfiles)
        self.find_orphan_files(allfiles, config.prefix, args.exclude)

    def find_duplicates(self, allfiles):
        count = collections.Counter(allfiles)
        duplicates = [x for x in count if count[x] > 1]
        if len(duplicates) > 0:
            m.message("Found duplicates files in packages:")
            m.message("%r" % duplicates)

    def find_orphan_files(self, allfiles, prefix, excludes=[]):
        cmd = 'find . -type f %s'
        exc = map(lambda x: "\\( ! -name '%s' \\)" % x, excludes)
        cmd = cmd % ' '.join(exc)

        distfiles = shell.check_call(cmd, prefix).split('\n')
        # remove './' from the list of files
        distfiles = [f[2:] for f in distfiles]
        orphan = sorted(list((set(distfiles) - set(allfiles))))

        if len(orphan) > 0:
            m.message("Found orphan files:")
            m.message('\n'.join(orphan))


register_command(DebugPackages)
