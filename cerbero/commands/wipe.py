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
import shutil

from cerbero.commands import Command, register_command
from cerbero.config import CONFIG_DIR
from cerbero.utils import _, N_, shell
import cerbero.utils.messages as m


class Wipe(Command):
    doc = N_('Wipes everything to restore the build system')
    name = 'wipe'

    def __init__(self):
        Command.__init__(self, [])

    def run(self, config, args):
        to_remove = [os.path.join(CONFIG_DIR, config.cache_file)]
        to_remove.append(config.prefix)
        to_remove.append(config.sources)

        options = ['yes', 'no']
        msg = _("WARNING!!!\n"
                "This command will delete cerbero's build cache, "
                "the sources directory and the builds directory "
                "to reset the build system to its initial state.\n"
                "The following paths will be removed:\n%s\n"
                "Do you want to continue? " % '\n'.join(to_remove))
        # Ask once
        if shell.prompt(msg, options) == options[0]:
            msg = _("Are you sure?")
            # Ask twice
            if shell.prompt(msg, options) == options[0]:
                # Start with the Apocalypse
                self.wipe(to_remove)

    def wipe(self, paths):
        for path in paths:
            m.action(_("Removing path: %s") % path)
            shutil.rmtree(path)


register_command(Wipe)
