#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2024 L. E. Segovia <amy@centricular.com>
# SPDX-License-Ref: LGPL-2.1-or-later

import subprocess
import os
from sys import stdout, stderr
from argparse import ArgumentParser, REMAINDER

parser = ArgumentParser(
    description='Convert command paths to Wine paths',
    epilog="Prepend 'posix:' to any path that must be converted. Alternatively, use '--' to separate flags from positional arguments. The positional arguments will be converted wholesale without further intervention.",
)
parser.add_argument('command_or_param', nargs=REMAINDER, help='Portion of command to call')

if __name__ == '__main__':
    args = parser.parse_args()
    new_argv = []
    convert_all = False
    for i in args.command_or_param:
        if i.startswith('posix:'):
            real_i = i[6:]
            if os.path.isdir(real_i):
                new_argv.append(f'z:{os.path.abspath(real_i)}/')
            else:
                new_argv.append(f'z:{os.path.abspath(real_i)}')
        elif i == '--':
            convert_all = True
        elif convert_all:
            new_argv.append(f'z:{os.path.abspath(i)}')
        else:
            new_argv.append(i)
    subprocess.check_call(
        new_argv,
        stdout=stdout,
        stderr=stderr,
        shell=False,  # Disallow interpreting the path to WiX v5
    )
