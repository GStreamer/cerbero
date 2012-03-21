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
import tempfile

from cerbero.utils import shell


class Package(object):
    '''
    Creates an osx package from a L{cerbero.packages.package.Package}

    @ivar package: package with the info to build the merge package
    @type package: L{cerbero.packages.package.Package}
    '''

    def __init__(self, config, package):
        self.config = config
        self.package = package
        self.files_list = package.get_files_list()

    def build(self, output_dir):
        output_dir = os.path.realpath(output_dir)
        output_file = os.path.join(output_dir, "%s.pkg" % self.package.name)

        root = self._create_bundle()
        packagemaker = PackageMaker()
        packagemaker.create_package(root, self.package.uuid,
                                    self.package.version, self.package.title,
                                    output_file)

    def _create_bundle(self, files):
        '''
        Moves all the files that are going to be package to a temporary
        directory to create the bundle
        '''
        tmp = tempfile.mkdtemp()
        for f in files:
            os.move(os.path.join(self.config.prefix, f), os.path.join(tmp, f))
        return tmp



class PackageMaker(object):
    ''' Warpper for the PackageMaker application '''

    PACKAGE_MAKER_PATH = \
        '/Developer/Applications/Utilities/PackageMaker.app/Contents/MacOS/'
    CMD = 'PackageMaker'

    def create_package(self, root, pkg_id, version, title, output_file,
                       destination='/opt/'):
        '''
        Creates an osx package, where all files are properly bundled in a
        directory that is set as the package root
        
        @param root: root path
        @type  root: str
        @param pkg_id: package indentifier
        @type  pkg_id: str
        @param version: package version
        @type  version: str
        @param title: package title
        @type  title: str
        @param output_file: path of the output file
        @type  output_file: str
        @param destination: installation path
        @type  destination: str
        '''
        args = {'r': root, 'i': pkg_id, '-n': version, 't': title,
                'l': destination, 'o': output_file}
        self._execute(self._cmd_with_options(args))

    def _set_cmd_options(self, args):
        args_str = ''
        for k, v in args.iteritems():
            args_str += ' -%s %s' % (k, v)
        return "%s %s" % (self.CMD, args_str)

    def _execute(self, cmd):
        shell.call(self.cmd)
