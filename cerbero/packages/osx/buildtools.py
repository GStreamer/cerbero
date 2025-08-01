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


class PackageBuild(object):
    """Wrapper for the packagebuild application"""

    CMD = 'pkgbuild'

    def create_package(
        self, root, pkg_id, version, title, output_file, destination='/opt/', scripts_path=None, min_os_version='10.13'
    ):
        """
        Creates an osx flat package, where all files are properly bundled in a
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
        """
        args = {
            'root': root,
            'identifier': pkg_id,
            'version': version,
            'install-location': destination,
            'compression': 'latest',
            'min-os-version': min_os_version,
        }
        if scripts_path is not None:
            args['scripts'] = scripts_path
        shell.new_call(self._cmd_with_args(args, output_file))

    def _cmd_with_args(self, args, output):
        args_arr = []
        for k, v in args.items():
            args_arr += ['--%s' % (k,), '%s' % (v,)]
        return [self.CMD] + args_arr + [output]


class ProductBuild(object):
    """Wrapper for the packagebuild application"""

    CMD = 'productbuild'

    def create_app_package(self, app_bundle, output):
        shell.new_call([self.CMD, '--component', app_bundle, '/Applications', output])

    def create_package(self, distribution, output, package_path=None):
        cmd = [self.CMD, '--distribution', distribution, output]
        for p in package_path:
            cmd += ['--package-path', p]
        shell.new_call(cmd)
