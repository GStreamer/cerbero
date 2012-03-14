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


__all__ = ['Command', 'register_command', 'run']


from cerbero.errors import FatalError
from cerbero.utils import _
from cerbero.utils import messages as m


class Command:
    """Base class for Command objects"""

    doc = ''
    name = None

    def __init__(self, arguments=[]):
        self.arguments = arguments

    def run(self, config, args):
        """The body of the command"""
        raise NotImplementedError

    def add_parser(self, subparsers):
        self.parser = subparsers.add_parser(self.name, help=_(self.doc))
        for arg in self.arguments:
            arg.add_to_parser(self.parser)


# dictionary with the list of commands
# command_name -> command_instance
_commands = {}


def register_command(command_class):
    command = command_class()
    _commands[command.name] = command


def load_commands(subparsers):
    import os
    commands_dir = os.path.abspath(os.path.dirname(__file__))

    for name in os.listdir(commands_dir):
        name, extension = os.path.splitext(name)
        if extension != '.py':
            continue
        try:
            __import__('cerbero.commands.%s' % name)
        except ImportError, e:
            m.warning("Error importing command %s:\n %s" % (name, e))
    for command in _commands.values():
        command.add_parser(subparsers)


def run(command, config, args):
    # if the command hasn't been registered, load a module by the same name
    if command not in _commands:
        raise FatalError(_('command not found'))

    return _commands[command].run(config, args)
