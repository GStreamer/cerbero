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

import sys
import os
import errno
import argparse
import logging
import traceback

from cerbero import config, commands
from cerbero.errors import UsageError, FatalError, BuildStepError
from cerbero.utils import _, N_, user_is_root

description = N_('Build and package a set of modules to distribute them in '\
                 'a SDK')


class Main(object):

    def __init__(self, args):
        if user_is_root():
            raise FatalError(_("cerbero can't be run as root"))

        self.init_logging()
        self.create_parser()
        self.load_commands()
        self.parse_arguments(args)
        self.load_config()
        self.run_command()

    def log_error(self, msg, print_usage=False):
        ''' Log an error and exit '''
        sys.stderr.write('%s\n' % msg)
        if print_usage:
            self.parser.print_usage()
        sys.exit(1)

    def init_logging(self):
        ''' Initialize logging '''
        logging.getLogger().setLevel(logging.INFO)
        logging.getLogger().addHandler(logging.StreamHandler())

    def create_parser(self):
        ''' Creates the arguments parser '''
        self.parser = argparse.ArgumentParser(description=_(description))
        self.parser.add_argument('--config', type=str, default=None,
                                 help=_('Configuration file used for the build'))

    def parse_arguments(self, args):
        ''' Parse the command line arguments '''
        self.args = self.parser.parse_args(args)

    def load_commands(self):
        subparsers = self.parser.add_subparsers(help=_('sub-command help'),
                                                dest='command')
        commands.load_commands(subparsers)

    def load_config(self):
        ''' Load the configuration '''
        try:
            self.config = config.Config(self.args.config)
        except FatalError, exc:
            traceback.print_exc()
            self.log_error(exc)

    def run_command(self):
        command = self.args.command
        try:
            res = commands.run(command, self.config, self.args)
        except UsageError, exc:
            self.log_error('cerbero %s: %s\n' % (command, exc), True)
            sys.exit(1)
        except FatalError, exc:
            traceback.print_exc()
            self.log_error('cerbero %s: %s\n' % (command, exc), True)
        except BuildStepError, exc:
            self.log_error('cerbero %s: %s\n' % (command, exc))
        except KeyboardInterrupt:
            self.log_error(_('Interrupted'))
        except IOError, e:
            if e.errno != errno.EPIPE:
                raise
            sys.exit(0)

        if res:
            sys.exit(res)


if __name__ == "__main__":
    Main(sys.argv[1:])
