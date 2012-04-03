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

import subprocess
import sys


class PkgConfig(object):
    '''
    Thin wrapper around pkg-config. This file is ment to be installed without
    cerbero and therefore can't import the shell utils
    '''

    cmd = 'pkg-config'

    def __init__(self, libs):
        self.libs = libs

    def headers_search_path(self):
        return self._exec('--cflags-only-I', 'I')

    def cflags(self):
        return self._exec('--clags-only-other')

    def libraries_search_path(self):
        return self._exec('--libs-only-L', 'L')

    def libraries(self):
        return self._exec('--libs-only-l')

    def _exec(self, mode, delimiter=None):
        cmd = '%s %s %s' % (self.cmd, mode, ' '.join(self.libs))
        process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
        output, unused_err = process.communicate()
        output = output.strip()
        if delimiter:
            output = ' '.join(output.split('-%s' % delimiter)[1:])
        return output


XCCONFIG_TPL = '''
ALWAYS_SEARCH_USER_PATHS = YES
USER_HEADER_SEARCH_PATHS = %(hsp)s
LIBRARY_SEARCH_PATHS = %(lsp)s
OTHER_LDFLAGS = %(libs)s
'''


class XCConfig(object):
    '''
    Creates an xcode config file to compile and link against the SDK using
    pkgconfig to guess the headers search path, the libraries search path and
    the libraries that need to be linked.
    '''

    def __init__(self, libraries):
        self.pkgconfig = PkgConfig(libraries)

    def create(self, outfile):
        args = dict()
        args['hsp'] = self.pkgconfig.headers_search_path()
        args['lsp'] = self.pkgconfig.libraries_search_path()
        args['libs'] = self.pkgconfig.libraries()
        with open(outfile, 'w') as f:
            f.write(XCCONFIG_TPL % args)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print "usage: xcconfig output_file libraries"
        sys.exit(1)
    xcconfig = XCConfig(sys.argv[2:])
    xcconfig.create(sys.argv[1])
