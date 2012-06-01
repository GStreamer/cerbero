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

import cerbero.utils.messages as m
from cerbero.errors import EmptyPackageError, MissingPackageFilesError
from cerbero.utils import _


class PackageType(object):

    RUNTIME = ''
    DEVEL = '-devel'
    DEBUG = '-debug'


class PackagerBase(object):
    ''' Base class for packagers '''

    def __init__(self, config, package, store):
        self.config = config
        self.package = package
        self.store = store

    def pack(self, output_dir, devel=True, force=False, keep_temp=False):
        '''
        Creates a package and puts it the the output directory

        @param output_dir: output directory where the package will be saved
        @type  output_dir: str
        @param devel: build the development version of this package
        @type  devel: bool
        @param force: forces the creation of the package
        @type  force: bool
        @param keep_temp: do not delete temporary files
        @type  force: bool

        @return: list of filenames for the packages created
        @rtype: list
        '''
        self.output_dir = os.path.realpath(output_dir)
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        self.devel = devel
        self.force = force
        self.keep_temp = keep_temp

    def files_list(self, package_type, force):
        if package_type == PackageType.DEVEL:
            files = self.package.devel_files_list()
        else:
            files = self.package.files_list()
        real_files = []
        for f in files:
            if os.path.exists(os.path.join(self.config.prefix, f)):
                real_files.append(f)
        diff = list(set(files) - set(real_files))
        if len(diff) != 0:
            if force:
                m.warning(_("Some files required by this package are missing "
                            "in the prefix:\n%s" % '\n'.join(diff)))
            else:
                raise MissingPackageFilesError(diff)
        if len(real_files) == 0:
            raise EmptyPackageError(self.package.name)
        return real_files
