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

from cerbero.commands import Command, register_command
from cerbero.errors import UsageError
from cerbero.ide.xcode.xcconfig import XCConfig
from cerbero.utils import _, N_, ArgparseArgument
from cerbero.utils import messages as m


class GenXCodeConfig(Command):
    doc = N_('Generate XCode config files to use the SDK from VS')
    name = 'genxcconfig'

    def __init__(self):
        Command.__init__(self,
            [ArgparseArgument('-o', '--output_dir', default='.',
                help=_('output directory where .xcconfig files will be saved')),
            ArgparseArgument('-f', '--filename', default=None,
                help=_('filename of the .xcconfig file')),
            ArgparseArgument('libraries', nargs='*',
                help=_('List of libraries to include')),
            ])

    def run(self, config, args):
        self.runargs(config, args.output_dir, args.filename, args.libraries)

    def runargs(self, config, output_dir, filename, libraries):
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        if len(libraries) == 0:
            raise UsageError("You need to specify at least one library name")

        filename = filename or libraries[0]
        filepath = os.path.join(output_dir, '%s.xcconfig' % filename)

        xcconfig = XCConfig(libraries)
        xcconfig.create(filepath)
        m.action('Created %s.xcconfig' % filename)

        m.message('XCode config file were sucessfully created in %s' %
                  os.path.abspath(filepath))


register_command(GenXCodeConfig)
