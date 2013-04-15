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
#!/bin/sh

%s

%s
'''


class GenSdkShell(Command):
    doc = N_('Create a script with the shell environment for the SDK')
    name = 'gensdkshell'

    DEFAULT_CMD = '$SHELL "$@"'

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
        if cmd == None:
            cmd = self.DEFAULT_CMD
        env = {}
        prefix_env_name = 'GSTREAMER_SDK_ROOT'
        prefix_env = '${%s}' % prefix_env_name
        libdir = libdir.replace(prefix, prefix_env)
        env['PATH'] = \
            '%s/bin${PATH:+:$PATH}:/usr/local/bin:/usr/bin:/bin' % prefix_env
        env['LD_LIBRARY_PATH'] = \
            '%s${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}' % libdir
        env['PKG_CONFIG_PATH'] = '%s/lib/pkgconfig:%s/share/pkgconfig'\
             '${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}' % (prefix_env, prefix_env)
        env['XDG_DATA_DIRS'] = '%s/share${XDG_DATA_DIRS:+:$XDG_DATA_DIRS}:'\
                '/usr/local/share:/usr/share' % prefix_env
        env['XDG_CONFIG_DIRS'] = \
            '%s/etc/xdg${XDG_CONFIG_DIRS:+:$XDG_CONFIG_DIRS}:/etc/xdg' % prefix_env
        env['GST_REGISTRY'] = '${HOME}/.gstreamer-0.10/gstreamer-sdk-registry'
        env['GST_REGISTRY_1_0'] = '${HOME}/.cache/gstreamer-1.0/gstreamer-sdk-registry'
        env['GST_PLUGIN_SCANNER'] = \
                '%s/libexec/gstreamer-0.10/gst-plugin-scanner' % prefix_env
        env['GST_PLUGIN_SCANNER_1_0'] = \
                '%s/libexec/gstreamer-1.0/gst-plugin-scanner' % prefix_env
        env['PYTHONPATH'] = '%s/%s/site-packages${PYTHONPATH:+:$PYTHONPATH}'\
                % (prefix_env, py_prefix)
        env['CFLAGS'] = '-I%s/include ${CFLAGS}' % prefix_env
        env['CXXFLAGS'] = '-I%s/include ${CXXFLAGS}' % prefix_env
        env['LDFLAGS'] = '-L%s ${LDFLAGS}' % libdir
        env['GIO_EXTRA_MODULES'] = '%s/gio/modules' % libdir
        envstr = 'export %s="%s"\n' % (prefix_env_name, prefix)
        for e, v in env.iteritems():
            envstr += 'export %s="%s"\n' % (e, v)
        try:
            filepath = os.path.join(output_dir, name)

            if not os.path.exists(os.path.dirname(filepath)):
              os.mkdir(os.path.dirname(filepath))

            with open(filepath, 'w+') as f:
                f.write(SCRIPT_TPL % (envstr, cmd))
            shell.call("chmod +x %s" % filepath)
        except IOError, ex:
            raise FatalError(_("Error creating script: %s" % ex))


register_command(GenSdkShell)
