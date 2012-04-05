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

from cerbero.config import Platform
from cerbero.commands import Command, register_command
from cerbero.errors import UsageError
from cerbero.build.cookbook import CookBook
from cerbero.utils import _, N_, ArgparseArgument
from cerbero.utils import messages as m

DEFAULT_PREFIX_MACRO = 'CERBERO_SDK_ROOT'


class GenLibraryFiles(Command):
    doc = N_('Generate MSVC compatible library files (.lib)')
    name = 'genlibfiles'

    def __init__(self):
        Command.__init__(self,
            [ArgparseArgument('-o', '--output_dir', default=None,
                help=_('output directory where .lib files will be saved')),
            ])

    def run(self, config, args):
        if config.target_platform != Platform.WINDOWS:
            raise UsageError(_('%s command can only be used targetting '
                             'Windows platforms') % self.name)

        if args.output_dir is not None and not os.path.exists(args.output_dir):
            os.makedirs(args.output_dir)

        cookbook = CookBook(config)
        recipes = cookbook.get_recipes_list()
        for recipe in recipes:
            try:
                recipe.gen_library_file(args.output_dir)
            except Exception, e:
                m.message(_("Error generaring library files for %s:\n %s") %
                          (recipe.name, e))


register_command(GenLibraryFiles)
