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
from cerbero.ide.common import PkgConfig
from cerbero.ide.vs.pkgconfig2vsprops import PkgConfig2VSProps, CommonVSProps
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
            ])

    def run(self, config, args):
        if not os.path.exists(args.output_dir):
            os.makedirs(args.output_dir)

        for pc in PkgConfig.list_all():
            m.action('Created %s.vsprops' % pc)
            p2v = PkgConfig2VSProps(pc, config.prefix, '$(%s)' %
                    DEFAULT_PREFIX_MACRO, False)
            p2v.create(args.output_dir)
            m.action('Created %s.vsprops' % pc)

        common = CommonVSProps(config.prefix, DEFAULT_PREFIX_MACRO)
        common.create(args.output_dir)
        m.message('Property sheets files were sucessfully created in %s' %
                  os.path.abspath(args.output_dir))


register_command(GenVSProps)
