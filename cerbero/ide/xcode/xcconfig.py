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

import sys
from cerbero.ide.pkgconfig import PkgConfig


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
        args = self._fill()
        with open(outfile, 'w') as f:
            f.write(XCCONFIG_TPL % args)

    def _fill(self):
        args = dict()
        args['hsp'] = ' '.join(self.pkgconfig.include_dirs())
        args['lsp'] = ' '.join(self.pkgconfig.libraries_dirs())
        args['libs'] = reduce(lambda x, y: '%s -l%s' % (x, y),
                              self.pkgconfig.libraries(), '')
        return args


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print "usage: xcconfig output_file libraries"
        sys.exit(1)
    xcconfig = XCConfig(sys.argv[2:])
    xcconfig.create(sys.argv[1])
