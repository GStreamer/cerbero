#!/usr/bin/env python
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

from cerbero.utils import shell


INT_CMD = 'install_name_tool'
OTOOL_CMD = 'otool'


class OSXRelocator(object):
    '''
    Wrapper for OS X's install_name_tool and otool commands to help
    relocating shared libraries.

    It parses lib/ /libexec and bin/ directories, changes the prefix path of
    the shared libraries that an object file uses and changes it's library
    ID if the file is a shared library.
    '''

    def __init__(self, root, lib_prefix, new_lib_prefix, recursive):
        self.root = root
        self.lib_prefix = self._fix_path(lib_prefix)
        self.new_lib_prefix = self._fix_path(new_lib_prefix)
        self.recursive = recursive

    def relocate(self):
        self.parse_dir(self.root)

    def relocate_file(self, object_file, id=None):
        self.change_libs_path(object_file)
        self.change_id(object_file, id)

    def change_id(self, object_file, id=None):
        id = id or object_file.replace(self.lib_prefix, self.new_lib_prefix)
        filename = os.path.basename(object_file)
        if not (filename.endswith('so') or filename.endswith('dylib')):
            return
        cmd = '%s -id %s %s' % (INT_CMD, id, object_file)
        shell.call(cmd)

    def change_libs_path(self, object_file):
        for lib in self.list_shared_libraries(object_file):
            if self.lib_prefix in lib:
                new_lib = lib.replace(self.lib_prefix, self.new_lib_prefix)
                cmd = '%s -change %s %s %s' % (INT_CMD, lib, new_lib,
                                               object_file)
                shell.call(cmd)

    def parse_dir(self, dir_path, filters=None):
        for dirpath, dirnames, filenames in os.walk(dir_path):
            for f in filenames:
                if filters is not None and \
                        os.path.splitext(f)[1] not in filters:
                    continue
                lib = os.path.join(dirpath, f)
                id = self.library_id_name(lib).replace(
                        self.lib_prefix, self.new_lib_prefix)
                self.change_libs_path(lib)
                self.change_id(lib, id)
            if not self.recursive:
                break

    @staticmethod
    def list_shared_libraries(object_file):
        cmd = '%s -L %s' % (OTOOL_CMD, object_file)
        res = shell.check_call(cmd).split('\n')
        # We don't use the first line
        libs = res[1:]
        # Remove the first character tabulation
        libs = [x[1:] for x in libs]
        # Remove the version info
        libs = [x.split(' ', 1)[0] for x in libs]
        return libs

    @staticmethod
    def library_id_name(object_file):
        cmd = '%s -D %s' % (OTOOL_CMD, object_file)
        res = shell.check_call(cmd).split('\n')[0]
        # the library name ends with ':'
        lib_name = res[:-1]
        return lib_name

    def _fix_path(self, path):
        if path.endswith('/'):
            return path[:-1]
        return path


class Main(object):

    def run(self):
        # We use OptionParser instead of ArgumentsParse because this script
        # might be run in OS X 10.6 or older, which do not provide the argparse
        # module
        import optparse
        usage = "usage: %prog [options] directory old_prefix new_prefix"
        description = 'Rellocates object files changing the dependant '\
                      ' dynamic libraries location path with a new one'
        parser = optparse.OptionParser(usage=usage, description=description)
        parser.add_option('-r', '--recursive', action='store_true',
                default=False, dest='recursive',
                help='Scan directories recursively')

        options, args = parser.parse_args()
        if len(args) != 3:
            parser.print_usage()
            exit(1)
        relocator = OSXRelocator(args[0], args[1], args[2], options.recursive)
        relocator.relocate()
        exit(0)


if __name__ == "__main__":
    main = Main()
    main.run()
