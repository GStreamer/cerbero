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

from cerbero.config import Architecture
from cerbero.errors import FatalError

# We only support Visual Studio 2015 as of now
vcvarsalls = {
    '14.0': [r'C:\Program Files (x86)\Microsoft Visual Studio 14.0\VC\vcvarsall.bat',
             r'C:\Program Files\Microsoft Visual Studio 14.0\VC\vcvarsall.bat'],
    '15.0': [r'C:\Program Files (x86)\Microsoft Visual Studio 15.0\VC\vcvarsall.bat',
             r'C:\Program Files\Microsoft Visual Studio 15.0\VC\vcvarsall.bat'],
}

vcvarsall = None
for (version, paths) in vcvarsalls.items():
    for path in paths:
        # Find the location of the Visual Studio installation
        if os.path.isfile(path):
            vcvarsall = path
            break
if not vcvarsall:
    versions = ', '.join(vcvarsalls.keys())
    raise FatalError('Microsoft Visual Studio not found, looked for: ' + versions)

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
    output = subprocess.check_output(cmd, shell=True, universal_newlines=True)
    return output.split('\n')

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
