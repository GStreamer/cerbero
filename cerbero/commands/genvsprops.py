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
from cerbero.ide.pkgconfig import PkgConfig
from cerbero.ide.vs.pkgconfig2vsprops import PkgConfig2VSProps
from cerbero.ide.vs.props import CommonProps
from cerbero.utils import _, N_, ArgparseArgument
from cerbero.utils import messages as m

DEFAULT_PREFIX_MACRO = 'CERBERO_SDK_ROOT'


class GenVSProps(Command):
    doc = N_('Generate Visual Studio property sheets to use the SDK from VS')
    name = 'genvsprops'

    def __init__(self):
        Command.__init__(self,
            [ArgparseArgument('-o', '--output_dir', default='.',
                help=_('output directory where .vsprops files will be saved')),
             ArgparseArgument('-p', '--prefix', default=DEFAULT_PREFIX_MACRO,
                 help=_('name of the prefix environment variable '
                        '(eg:CERBERO_SDK_ROOT_X86)')),
            ])

    def run(self, config, args):
        self.runargs(config, args.output_dir, args.prefix)

    def runargs(self, config, output_dir, prefix=DEFAULT_PREFIX_MACRO):
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        for pc in PkgConfig.list_all():
            p2v = PkgConfig2VSProps(pc, prefix=config.prefix,
                    inherit_common=True,
                    prefix_replacement='$(%s)' % prefix)
            p2v.create(output_dir)
            m.action('Created %s.props' % pc)

        common = CommonProps(prefix)
        common.create(output_dir)

        m.message('Property sheets files were sucessfully created in %s' %
                  os.path.abspath(output_dir))


register_command(GenVSProps)
