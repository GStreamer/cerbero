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


class GenLib(object):
    '''
    Generates an import library that can be used in Visual Studio from a DLL,
    using 'gendef' to create a .def file and than libtool to create the import
    library 
    '''

    DLLTOOL_TPL = '$DLLTOOL -d %s -l %s -D %s'

    def create(self, dllpath, outputdir=None):
        bindir, dllname = os.path.split(dllpath)
        if outputdir is None:
            outputdir = bindir

        # Create the .def file
        shell.call('gendef %s' % dllpath, outputdir)
        if '-' in dllname:
            # libfoo-1.0-0.dll -> libfoo-1.0
            libname = dllname.rsplit('-', 1)[0]
        else:
            # libfoo.dll
            libname = dllname.rsplit('.', 1)[0]

        defname = dllname.replace('.dll', '.def')
        implib = '%s.lib' % libname

        # Create the import library
        shell.call(self.DLLTOOL_TPL % (defname, implib, dllname), outputdir)
        return os.path.join(outputdir, implib)
