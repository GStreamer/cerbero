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


class PackagerBase(object):
    ''' Base class for packagers '''

    def __init__(self, config, package, store):
        self.config = config
        self.package = package
        self.store = store

    def pack(self, output_dir, force=False):
        '''
        Creates a package and puts it the the output directory

        @param output_dir: output directory where the package will be saved
        @type  output_dir: str
        @param force: forces the creation of the package
        @type  force: bool
        '''
        raise NotImplemented("'pack' must be implemented by subclasses")
