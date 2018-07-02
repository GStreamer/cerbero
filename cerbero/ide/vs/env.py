# cerbero - a multi-platform build system for Open Source software
# Copyright (C) 2016 Nirbheek Chauhan <nirbheek@centricular.com>
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
import subprocess
from pathlib import Path

from cerbero.config import Architecture
from cerbero.errors import FatalError

# We only support Visual Studio 2015 as of now
vcvarsalls = {
    '14.0': [r'Microsoft Visual Studio 14.0\VC\vcvarsall.bat'],
    '15.0': [r'Microsoft Visual Studio\2017\Community\VC\Auxiliary\Build\vcvarsall.bat',
             r'Microsoft Visual Studio\2017\Professional\VC\Auxiliary\Build\vcvarsall.bat'],
}
program_files = Path(os.environ['PROGRAMFILES(X86)'])

vcvarsall = None
for version in sorted(vcvarsalls.keys(), reverse=True):
    if vcvarsall:
        break
    for path in vcvarsalls[version]:
        path = program_files / path
        # Find the location of the Visual Studio installation
        if path.is_file():
            vcvarsall = path.as_posix()
            break
if not vcvarsall:
    versions = ', '.join(vcvarsalls.keys())
    raise FatalError('Microsoft Visual Studio not found, please file a bug. We looked for: ' + versions)

def append_path(var, path, sep=';'):
    if var and not var.endswith(sep):
        var += sep
    if path and not path.endswith(sep):
        path += sep
    var += path
    return var

def get_vcvarsall_arg(arch, target_arch):
    if target_arch == Architecture.X86:
        # If arch is x86_64, this will cause the WOW64 version of MSVC to be
        # used, which is how most people compile 32-bit apps on 64-bit.
        return 'x86'
    if arch == Architecture.X86:
        if target_arch == Architecture.X86_64:
            return 'x86_amd64'
        elif target_arch.is_arm():
            return 'x86_arm'
    elif arch == Architecture.X86_64:
        if target_arch == Architecture.X86_64:
            return 'amd64'
        elif target_arch.is_arm():
            return 'amd64_arm'
    elif arch.is_arm() and target_arch.is_arm():
            return 'arm'
    raise FatalError('Unsupported arch/target_arch: {0}/{1}'.format(arch, target_arch))

def run_and_get_env(cmd):
    env = os.environ.copy()
    env['VSCMD_ARG_no_logo'] = '1'
    env['VSCMD_DEBUG'] = ''
    output = subprocess.check_output(cmd, shell=True, env=env,
                                     universal_newlines=True)
    lines = []
    for line in output.split('\n'):
        if '=' in line:
            lines.append(line)
    return lines

def get_msvc_env(vcvarsall, arch, target_arch):
    ret_env = {}
    if not os.path.isfile(vcvarsall):
        raise FatalError("'{0}' not found".format(vcvarsall))

    without_msvc = run_and_get_env('set')
    arg = get_vcvarsall_arg(arch, target_arch)
    vcvars_env_cmd = '"{0}" {1} & {2}'.format(vcvarsall, arg, 'set')
    with_msvc = run_and_get_env(vcvars_env_cmd)

    for each in set(with_msvc) - set(without_msvc):
        (var, value) = each.split('=', 1)
        ret_env[var] = value
    return ret_env
