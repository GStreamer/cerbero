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
import argparse

from cerbero.errors import FatalError
from cerbero.ide.vs.props import Props
from cerbero.ide.vs.vsprops import VSProps
from cerbero.ide.pkgconfig import PkgConfig
from cerbero.utils import messages as m


class PkgConfig2VSProps(object):

    generators = {'vs2008': VSProps, 'vs2010': Props}

    def __init__(self, libname, target='vs2010', prefix=None,
            prefix_replacement=None, inherit_common=False):

        if target not in self.generators:
            raise FatalError('Target version must be one of %s' %
                             generators.keys())

        pkgconfig = PkgConfig([libname], False)
        requires = pkgconfig.requires()
        include_dirs = pkgconfig.include_dirs()
        libraries_dirs = pkgconfig.libraries_dirs()

        libs = pkgconfig.libraries()
        if None not in [prefix_replacement, prefix]:
            libraries_dirs = [x.replace(prefix, prefix_replacement)
                    for x in libraries_dirs]
            include_dirs = [x.replace(prefix, prefix_replacement)
                    for x in include_dirs]
        self.vsprops = self.generators[target](libname, requires, include_dirs,
                libraries_dirs, libs, inherit_common)

    def create(self, outdir):
        self.vsprops.create(outdir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Creates VS property '
        'sheets with pkg-config')
    parser.add_argument('library', help='Library name')
    parser.add_argument('-o', type=str, default='.',
                    help='Output directory for generated files')
    parser.add_argument('-c', type=str, default='vs2010',
                    help='Target version (vs2008 or vs2010) name')

    generators = {'vs2008': VSProps, 'vs2010': Props}
    args = parser.parse_args(sys.argv[1:])
    try:
        p2v = PkgConfig2VSProps(args.library, args.c)
        p2v.create(args.o)
    except Exception, e:
        import traceback
        traceback.print_exc()
        m.error(str(e))
        exit(1)
    exit(0)
