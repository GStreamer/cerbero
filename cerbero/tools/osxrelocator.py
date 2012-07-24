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
import subprocess


class OSXRelocator(object):
    '''
    Wrapper for OS X's install_name_tool and otool commands to help
    relocating shared libraries.

    It parses lib/ /libexec and bin/ directories, changes the prefix path of
    the shared libraries that an object file uses and changes it's library
    ID if the file is a shared library.
    '''

    INT_CMD = 'install_name_tool'
    OTOOL_CMD = 'otool'

    def __init__(self, root, lib_prefix, new_lib_prefix, recursive):
        self.root = root
        self.lib_prefix = lib_prefix
        self.new_lib_prefix = new_lib_prefix
        self.recursive = recursive

    def relocate(self):
        self.parse_dir(self.root)

    def relocate_file(self, path):
        self.change_libs_path(path)

    def change_id(self, lib_id):
        cmd = '%s -id %s' % (self.INT_CMD, self.lib_id)
        self._call(cmd)

    def change_libs_path(self, object_file):
        print "Fixing object file %s" % object_file
        for lib in self.list_shared_libraries(object_file):
            if self.lib_prefix in lib:
                new_lib = lib.replace(self.lib_prefix, self.new_lib_prefix)
                cmd = '%s -change %s %s %s' % (self.INT_CMD, lib, new_lib,
                                               object_file)
                self._call(cmd)

    def list_shared_libraries(self, object_file):
        cmd = '%s -L %s' % (self.OTOOL_CMD, object_file)
        res = self._call(cmd).split('\n')
        # We don't use the first line
        libs = res[1:]
        # Remove the first character tabulation
        libs = [x[1:] for x in libs]
        # Remove the version info
        libs = [x.split(' ', 1)[0] for x in libs]
        return libs

    def parse_dir(self, dir_path, filters=None):
        for dirpath, dirnames, filenames in os.walk(dir_path):
            for f in filenames:
                if filters is not None and os.path.splitext(f)[1] not in filters:
                    continue
                self.change_libs_path(os.path.join(dirpath, f))
            if not self.recursive:
                break

    def _call(self, cmd, cwd=None):
        cmd = cmd or self.root
        process = subprocess.Popen(cmd, cwd=cwd,
            stdout=subprocess.PIPE, shell=True)
        output, unused_err = process.communicate()
        return output



class Main(object):

    def run(self):
        # We use OptionParser instead of ArgumentsParse because this script might
        # be run in OS X 10.6 or older, which do not provide the argparse module
        import optparse
        usage = "usage: %prog [options] directory old_prefix new_prefix"
        description='Rellocates object files changing the dependant dynamic '\
                    'libraries location path with a new one'
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
