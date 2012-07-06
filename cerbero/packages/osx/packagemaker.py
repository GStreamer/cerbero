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

from cerbero.utils import shell


class PackageMaker(object):
    ''' Wrapper for the PackageMaker application '''

    PACKAGE_MAKER_PATH = \
        '/Developer/Applications/Utilities/PackageMaker.app/Contents/MacOS/'
    CMD = './PackageMaker'

    def create_package(self, root, pkg_id, version, title, output_file,
                       destination='/opt/', target='10.5',
                       scripts_path=None):
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
        @param scripts_path: relative path for package scripts
        @type  scripts_path: str
        '''
        args = {'r': root, 'i': pkg_id, 'n': version, 't': title,
                'l': destination, 'o': output_file}
        if scripts_path is not None:
            args['s'] = scripts_path
        if target is not None:
            args['g'] = target
        self._execute(self._cmd_with_args(args))

    def create_package_from_pmdoc(self, pmdoc_path, output_file):
        '''
        Creates an osx package from a pmdoc configuration files
        '''
        args = {'d': pmdoc_path, 'o': output_file}
        self._execute(self._cmd_with_args(args))

    def _cmd_with_args(self, args):
        args_str = ''
        for k, v in args.iteritems():
            args_str += " -%s '%s'" % (k, v)
        return '%s %s' % (self.CMD, args_str)

    def _execute(self, cmd):
        shell.call(cmd, self.PACKAGE_MAKER_PATH)
