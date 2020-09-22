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

import asyncio
import argparse

from cerbero.commands import Command, register_command
from cerbero.utils import N_, _, ArgparseArgument, determine_num_of_cpus, run_until_complete, StoreBool
from cerbero.utils import messages as m
from cerbero.bootstrap.bootstrapper import Bootstrapper

NUMBER_OF_JOBS_IF_UNUSED = 2
NUMBER_OF_JOBS_IF_USED = 2 * determine_num_of_cpus()

class Bootstrap(Command):
    doc = N_('Bootstrap the build system installing all the dependencies')
    name = 'bootstrap'

    def __init__(self):
        args = [
            ArgparseArgument('--build-tools-only', action='store_true',
                default=False, help=argparse.SUPPRESS),
            ArgparseArgument('--system-only', action='store_true',
                default=False, help=argparse.SUPPRESS),
            ArgparseArgument('--system', action=StoreBool,
                default=True, nargs='?', choices=('yes', 'no'),
                help='Setup the system for building, such as by installing system packages'),
            ArgparseArgument('--toolchains', action=StoreBool,
                default=True, nargs='?', choices=('yes', 'no'),
                help='Setup any toolchains needed by the target platform'),
            ArgparseArgument('--build-tools', action=StoreBool,
                default=True, nargs='?', choices=('yes', 'no'),
                help='Compile the build tools needed while building'),
            ArgparseArgument('--offline', action='store_true',
                default=False, help=_('Use only the source cache, no network')),
            ArgparseArgument('-y', '--assume-yes', action='store_true',
                default=False, help=('Automatically say yes to prompts and run non-interactively')),
            ArgparseArgument('--jobs', '-j', action='store', type=int,
                default=0, help=_('How many recipes to build concurrently. '
                        '0 = number of CPUs.'))]
        Command.__init__(self, args)

    def run(self, config, args):
        if args.build_tools_only:
            # --build-tools-only meant '--system=no --toolchains=no --build-tools=yes'
            args.toolchains = False
            args.system = False
            m.deprecation('Replace --build-tools-only with --system=no --toolchains=no')
        if args.system_only:
            # --system-only meant '--system=yes --toolchains=yes --build-tools=no'
            args.build_tools = False
            m.deprecation('Replace --system-only with --build-tools=no')
        bootstrappers = Bootstrapper(config, args.system, args.toolchains,
                args.build_tools, args.offline, args.assume_yes)
        tasks = []
        async def bootstrap_fetch_extract(bs):
            await bs.fetch()
            await bs.extract()
        for bootstrapper in bootstrappers:
            tasks.append(bootstrap_fetch_extract(bootstrapper))
        run_until_complete(tasks)

        for bootstrapper in bootstrappers:
            bootstrapper.start(jobs=args.jobs)


class FetchBootstrap(Command):
    doc = N_('Fetch the sources required for bootstrap')
    name = 'fetch-bootstrap'

    def __init__(self):
        args = [
            ArgparseArgument('--build-tools-only', action='store_true',
                default=False, help=argparse.SUPPRESS),
            ArgparseArgument('--toolchains', action=StoreBool,
                default=True, nargs='?', choices=('yes', 'no'),
                help='Setup any toolchains needed by the target platform'),
            ArgparseArgument('--build-tools', action=StoreBool,
                default=True, nargs='?', choices=('yes', 'no'),
                help='Compile the build tools needed while building'),
            ArgparseArgument('--jobs', '-j', action='store', nargs='?', type=int,
                    const=NUMBER_OF_JOBS_IF_USED, default=NUMBER_OF_JOBS_IF_UNUSED, help=_('number of async jobs'))]
        Command.__init__(self, args)

    def run(self, config, args):
        if args.build_tools_only:
            # --build-tools-only meant '--toolchains=no --build-tools=yes'
            args.toolchains = False
            m.deprecation('Replace --build-tools-only with --toolchains=no')
        bootstrappers = Bootstrapper(config, False, args.toolchains,
                args.build_tools, offline=False, assume_yes=False)
        tasks = []
        for bootstrapper in bootstrappers:
            bootstrapper.fetch_recipes(args.jobs)
            tasks.append(bootstrapper.fetch())
        run_until_complete(tasks)

register_command(Bootstrap)
register_command(FetchBootstrap)
