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
from cerbero.errors import FatalError
from cerbero.utils import _, N_, ArgparseArgument, shell


SCRIPT_TPL = '''\
#!/bin/bash

%s

%s
'''


class GenSdkShell(Command):
    doc = N_('Create a script with the shell environment for the SDK')
    name = 'gensdkshell'

    DEFAULT_CMD = 'exec "$@"'

    def __init__(self):
        Command.__init__(self,
            [ArgparseArgument('name', nargs=1, default='sdk-shell',
                             help=_('name of the scrips')),
            ArgparseArgument('-o', '--output-dir', default='.',
                             help=_('output directory')),
            ArgparseArgument('-p', '--prefix',
                             help=_('prefix of the SDK')),
            ArgparseArgument('--cmd', default=self.DEFAULT_CMD,
                             help=_('command to run in the script')),
            ])

    def run(self, config, args):
        name = args.name[0]
        prefix = args.prefix and args.prefix or config.prefix
        libdir = os.path.join(prefix, 'lib')
        py_prefix = config.py_prefix
        output_dir = args.output_dir
        cmd = args.cmd
        self.runargs(config, name, output_dir, prefix, libdir, py_prefix, cmd)

    def runargs(self, config, name, output_dir, prefix, libdir,
                py_prefix, cmd=None):
        cmd = cmd or self.DEFAULT_CMD
        env = config.get_env(prefix, libdir, py_prefix)
        env['PATH'] = '%s/bin:$PATH' % prefix
        env['LDFLAGS'] = '-L%s' % libdir
        envstr = ''
        for e, v in env.iteritems():
            v = v.replace(config.prefix, prefix)
            envstr += '%s="%s"\n' % (e, v)
        try:
            filepath = os.path.join(output_dir, name)
            with open(filepath, 'w+') as f:
                f.write(SCRIPT_TPL % (envstr, cmd))
            shell.call("chmod +x %s" % filepath)
        except IOError, ex:
            raise FatalError(_("Error creating script: %s", ex))


register_command(GenSdkShell)
