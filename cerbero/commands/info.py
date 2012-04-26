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
from cerbero.packages.packagesstore import PackagesStore
from cerbero.packages.package import MetaPackage


INFO_TPL = '''
Name:          %(name)s
Version:       %(version)s
Homepage:      %(url)s
Dependencies:  %(deps)s
Licences:      %(licenses)s
Description:   %(desc)s
'''


class PackageInfo(Command):
    doc = N_('Print information about this package')
    name = 'packageinfo'

    def __init__(self):
        Command.__init__(self,
            [ArgparseArgument('package', nargs=1,
                             help=_('name of the package')),
            ArgparseArgument('-l', '--list-files', action='store_true',
                default=False,
                help=_('List all files installed by this package')),
            ])

    def run(self, config, args):
        store = PackagesStore(config)
        p_name = args.package[0]
        if args.list_files:
            m.message('\n'.join(store.get_package_files_list(p_name)))
        else:
            p = store.get_package(p_name)
            licenses = [p.license]
            if not isinstance(p, MetaPackage):
                recipes_licenses = p.recipes_licenses()
                recipes_licenses.update(p.devel_recipes_licenses())
                for recipe_name, categories_licenses in \
                        recipes_licenses.iteritems():
                    for category_licenses in categories_licenses.itervalues():
                        licenses.extend(category_licenses)
            licenses = sorted(list(set(licenses)))
            d = {'name': p.name, 'version': p.version, 'url': p.url,
                 'licenses': ' and '.join([l.acronym for l in licenses]),
                 'desc': p.shortdesc,
                 'deps': ', '.join([p.name for p in
                                    store.get_package_deps(p_name, True)])}
            m.message(INFO_TPL % d)

register_command(PackageInfo)
