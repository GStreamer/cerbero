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
import re
import shlex
import shutil

from cerbero.enums import Architecture, Platform
from cerbero.utils import shell
from cerbero.utils import messages as m
from cerbero.errors import FatalError


class GenLib(object):
    '''
    Generates an import library that can be used in Visual Studio from a DLL,
    using 'gendef' to create a .def file and then libtool to create the import
    library (.lib)
    '''

    filename = 'unknown'

    def __init__(self, config, logfile):
        self.config = config
        self.logfile = logfile
        self.gendef_bin = shlex.split(self.config.env['GENDEF'])
        self.dlltool_bin = shlex.split(self.config.env['DLLTOOL'])

    def _fix_broken_def_output(self, contents):
        if self.config.target_arch != Architecture.X86:
            return contents
        out = ''
        broken_entry_re = re.compile(r'([a-zA-Z_]+@[0-9]+)@[0-9]+')
        for line in contents.split(os.linesep):
            line = self._fix_broken_entry(line, broken_entry_re)
            out += line + os.linesep
        return out

    def _fix_broken_entry(self, line, regex):
        if line.startswith(';'):
            return line
        m = regex.match(line)
        if not m:
            return line
        return m.groups()[0]

    def gendef(self, dllpath, outputdir, libname):
        defname = libname + '.def'
        def_contents = shell.check_output(self.gendef_bin + ['-', dllpath], outputdir,
                                          logfile=self.logfile, env=self.config.env)
        # If the output doesn't contain a 'LIBRARY' directive, gendef errored
        # out. However, gendef always returns 0 so we need to inspect the
        # output and guess.
        if 'LIBRARY' not in def_contents:
            raise FatalError('gendef failed on {!r}\n{}'.format(dllpath, def_contents))
        with open(os.path.join(outputdir, defname), 'w') as f:
            f.write(self._fix_broken_def_output(def_contents))
        return defname

    def dlltool(self, defname, dllname, outputdir):
        cmd = self.dlltool_bin + ['-d', defname, '-l', self.filename, '-D', dllname]
        shell.new_call(cmd, outputdir, logfile=self.logfile, env=self.config.env)

    def create(self, libname, dllpath, platform, target_arch, outputdir):
        # foo.lib must not start with 'lib'
        if libname.startswith('lib'):
            self.filename = libname[3:] + '.lib'
        else:
            self.filename = libname + '.lib'

        bindir, dllname = os.path.split(dllpath)

        # Create the .def file
        defname = self.gendef(dllpath, outputdir, libname)

        # Create the import library
        lib_path, paths = self._get_lib_exe_path(target_arch, platform)

        # Prefer LIB.exe over dlltool:
        # http://sourceware.org/bugzilla/show_bug.cgi?id=12633
        if lib_path is not None:
            if target_arch == Architecture.X86:
                arch = 'x86'
            else:
                arch = 'x64'
            env = self.config.env.copy()
            env['PATH'] = paths + ';' + env['PATH']
            cmd = [lib_path, '/DEF:' + defname, '/OUT:' + self.filename, '/MACHINE:' + arch]
            shell.new_call(cmd, outputdir, logfile=self.logfile, env=env)
        else:
            m.warning("Using dlltool instead of lib.exe! Resulting .lib files"
                " will have problems with Visual Studio, see "
                " http://sourceware.org/bugzilla/show_bug.cgi?id=12633")
            self.dlltool(defname, dllname, outputdir)
        return os.path.join(outputdir, self.filename)

    def _get_lib_exe_path(self, target_arch, platform):
        # No Visual Studio tools while cross-compiling
        if platform != Platform.WINDOWS:
            return None, None
        from cerbero.ide.vs.env import get_msvc_env
        msvc_env = get_msvc_env('x86', target_arch)[0]
        paths = msvc_env['PATH']
        return shutil.which('lib', path=paths), paths

class GenGnuLib(GenLib):
    '''
    Generates an import library (libfoo.dll.a; not foo.lib) that is in a format
    that allows GNU ld to resolve all symbols exported by a DLL created by MSVC.

    Usually everything works fine even if you pass a .lib import library created
    by MSVC to GNU GCC/LD, but it won't find any exported DATA (variable)
    symbols from the import library. It can find them if you pass it the DLL
    directly, but that's a terrible idea and breaks how library searching works,
    so we create a GNU-compatible import library which will always work.
    '''

    def create(self, libname, dllpath, platform, target_arch, outputdir):
        # libfoo.dll.a must start with 'lib'
        if libname.startswith('lib'):
            self.filename = libname + '.dll.a'
        else:
            self.filename = 'lib{0}.dll.a'.format(libname)
        dllname = os.path.basename(dllpath)
        # Create the .def file
        defname = self.gendef(dllpath, outputdir, libname)

        # Create the .dll.a file
        self.dlltool(defname, dllname, outputdir)
        return os.path.join(outputdir, self.filename)
