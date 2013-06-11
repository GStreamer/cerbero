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
import stat
import shutil

from cerbero.commands import Command, register_command
from cerbero.config import CONFIG_DIR
from cerbero.utils import _, N_, shell, ArgparseArgument
import cerbero.utils.messages as m


class Wipe(Command):
    doc = N_('Wipes everything to restore the build system')
    name = 'wipe'

    def __init__(self):
        Command.__init__(self, [
                ArgparseArgument('--force', action='store_true',
                    default=False,
                    help=_('force the deletion of everything without user '
                           'input')),
                ArgparseArgument('--build-tools', action='store_true',
                    default=False,
                    help=_('wipe the build tools too'))])

    def run(self, config, args):
        to_remove = [os.path.join(CONFIG_DIR, config.cache_file)]
        to_remove.append(config.prefix)
        to_remove.append(config.sources)
        if (args.build_tools):
            to_remove.append(os.path.join(CONFIG_DIR, config.build_tools_cache))
            to_remove.append(config.build_tools_prefix)
            to_remove.append(config.build_tools_sources)

        if args.force:
            self.wipe(to_remove)
            return

        options = ['yes', 'no']
        msg = _("WARNING!!!\n"
                "This command will delete cerbero's build cache, "
                "the sources directory and the builds directory "
                "to reset the build system to its initial state.\n"
                "The following paths will be removed:\n%s\n"
                "Do you want to continue?" % '\n'.join(to_remove))
        # Ask once
        if shell.prompt(msg, options) == options[0]:
            msg = _("Are you sure?")
            # Ask twice
            if shell.prompt(msg, options) == options[0]:
                # Start with the Apocalypse
                self.wipe(to_remove)

    def wipe(self, paths):

        def _onerror(func, path, exc_info):
            if not os.access(path, os.W_OK):
                os.chmod(path, stat.S_IWUSR)
                func(path)
            # Handle "Directory is not empty" errors
            elif exc_info[1][0] == 145:
                shutil.rmtree(path, onerror=_onerror)
            else:
                raise

        for path in paths:
            m.action(_("Removing path: %s") % path)
            if not os.path.exists(path):
                continue
            if os.path.isfile(path):
                if not os.access(path, os.W_OK):
                    os.chmod(path, stat.S_IWUSR)
                os.remove(path)
            else:
                shutil.rmtree(path, onerror=_onerror)


register_command(Wipe)
