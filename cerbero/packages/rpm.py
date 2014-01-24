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
import shutil
import tempfile

from cerbero.config import Architecture
from cerbero.errors import FatalError, EmptyPackageError
from cerbero.packages import PackageType
from cerbero.packages.linux import LinuxPackager
from cerbero.packages.package import MetaPackage
from cerbero.utils import shell, _


SPEC_TPL = '''
%%define _topdir %(topdir)s
%%define _package_name %(package_name)s

Name:           %(p_prefix)s%(name)s
Version:        %(version)s
Release:        1
Summary:        %(summary)s
Source:         %(source)s
Group:          Applications/Internet
License:        %(licenses)s
Prefix:         %(prefix)s
Packager:       %(packager)s
Vendor:         %(vendor)s
%(url)s
%(requires)s

%%description
%(description)s

%(devel_package)s

%%prep
%%setup -n %%{_package_name}

%%build

%%install
mkdir -p $RPM_BUILD_ROOT/%%{prefix}
cp -r $RPM_BUILD_DIR/%%{_package_name}/* $RPM_BUILD_ROOT/%%{prefix}

# Workaround to remove full source dir paths from debuginfo packages
# (tested in Fedora 16/17).
#
# What happens is that rpmbuild invokes find-debuginfo.sh which in turn
# calls debugedit passing $RPM_BUILD_DIR as the "base-dir" param (-b) value.
# debugedit then removes the "base-dir" path from debug information.
#
# Normally packages are built inside $RPM_BUILD_DIR, thus resulting in proper
# debuginfo packages, but as we are building our recipes at $sources_dir and
# only including binaries here directly, no path would be removed and debuginfo
# packages containing full paths to source files would be used.
#
# Setting RPM_BUILD_DIR to $sources_dir should do the trick, setting here and
# hoping for the best.
export RPM_BUILD_DIR=%(sources_dir)s

%%clean
rm -rf $RPM_BUILD_ROOT

%(scripts)s

%%files
%(files)s

%(devel_files)s
'''


DEVEL_PACKAGE_TPL = '''
%%package devel
%(requires)s
Summary: %(summary)s
Provides: %(p_prefix)s%(name)s-devel

%%description devel
%(description)s
'''

META_SPEC_TPL = '''
%%define _topdir %(topdir)s
%%define _package_name %(package_name)s

Name:           %(p_prefix)s%(name)s
Version:        %(version)s
Release:        1
Summary:        %(summary)s
Group:          Applications/Internet
License:        %(licenses)s
Packager:       %(packager)s
Vendor:         %(vendor)s
%(url)s

%(requires)s

%%description
%(description)s

%(devel_package)s

%%prep

%%build

%%install

%%clean
rm -rf $RPM_BUILD_ROOT

%%files

%(devel_files)s
'''

REQUIRE_TPL = 'Requires: %s\n'
DEVEL_TPL = '%%files devel \n%s'
URL_TPL = 'URL: %s\n'
PRE_TPL = '%%pre\n%s\n'
POST_TPL = '%%post\n%s\n'
POSTUN_TPL = '%%postun\n%s\n'


class RPMPackager(LinuxPackager):

    def __init__(self, config, package, store):
        LinuxPackager.__init__(self, config, package, store)

    def create_tree(self, tmpdir):
        # create a tmp dir to use as topdir
        if tmpdir is None:
            tmpdir = tempfile.mkdtemp()
            for d in ['BUILD', 'SOURCES', 'RPMS', 'SRPMS', 'SPECS']:
                os.mkdir(os.path.join(tmpdir, d))
        return (tmpdir, os.path.join(tmpdir, 'RPMS'),
                os.path.join(tmpdir, 'SOURCES'))

    def setup_source(self, tarball, tmpdir, packagedir, srcdir):
        # move the tarball to SOURCES
        shutil.move(tarball, srcdir)
        tarname = os.path.split(tarball)[1]
        return tarname

    def prepare(self, tarname, tmpdir, packagedir, srcdir):
        try:
            runtime_files = self._files_list(PackageType.RUNTIME)
        except EmptyPackageError:
            runtime_files = ''

        if runtime_files or isinstance(self.package, MetaPackage):
            self.package.has_runtime_package = True
        else:
            self.package.has_runtime_package = False

        if self.devel:
            devel_package, devel_files = self._devel_package_and_files()
        else:
            devel_package, devel_files = ('', '')

        if isinstance(self.package, MetaPackage):
            template = META_SPEC_TPL
            requires = \
                self._get_meta_requires(PackageType.RUNTIME)
            self.package.has_devel_package = True
        else:
            self.package.has_devel_package = bool(devel_files)
            template = SPEC_TPL
            requires = self._get_requires(PackageType.RUNTIME)

        licenses = [self.package.license]
        if not isinstance(self.package, MetaPackage):
            licenses.extend(self.recipes_licenses())
            licenses = sorted(list(set(licenses)))

        scripts = ''
        if os.path.exists(self.package.resources_postinstall):
            scripts += POST_TPL % \
                open(self.package.resources_postinstall).read()
        if os.path.exists(self.package.resources_postremove):
            scripts += POSTUN_TPL % \
                open(self.package.resources_postremove).read()

        self._spec_str = template % {
                'name': self.package.name,
                'p_prefix': self.package_prefix,
                'version': self.package.version,
                'package_name': self.full_package_name,
                'summary': self.package.shortdesc,
                'description': self.package.longdesc != 'default' and \
                        self.package.longdesc or self.package.shortdesc,
                'licenses': ' and '.join([l.acronym for l in licenses]),
                'packager': self.packager,
                'vendor': self.package.vendor,
                'url': URL_TPL % self.package.url if \
                        self.package.url != 'default' else '',
                'requires': requires,
                'prefix': self.install_dir,
                'source': tarname,
                'topdir': tmpdir,
                'devel_package': devel_package,
                'devel_files': devel_files,
                'files': runtime_files,
                'sources_dir': self.config.sources,
                'scripts': scripts}

        self.spec_path = os.path.join(tmpdir, '%s.spec' % self.package.name)
        with open(self.spec_path, 'w') as f:
            f.write(self._spec_str)

    def build(self, output_dir, tarname, tmpdir, packagedir, srcdir):
        if self.config.target_arch == Architecture.X86:
            target = 'i686-redhat-linux'
        elif self.config.target_arch == Architecture.X86_64:
            target = 'x86_64-redhat-linux'
        else:
            raise FatalError(_('Architecture %s not supported') % \
                             self.config.target_arch)
        shell.call('rpmbuild -bb --buildroot %s/buildroot --target %s %s' % (tmpdir,
            target, self.spec_path))

        paths = []
        for d in os.listdir(packagedir):
            for f in os.listdir(os.path.join(packagedir, d)):
                out_path = os.path.join(output_dir, f)
                if os.path.exists(out_path):
                    os.remove(out_path)
                paths.append(out_path)
                shutil.move(os.path.join(packagedir, d, f), output_dir)
        return paths

    def _get_meta_requires(self, package_type):
        devel_suffix = ''
        if package_type == PackageType.DEVEL:
            devel_suffix = '-devel'
        requires, recommends, suggests = \
            self.get_meta_requires(package_type, devel_suffix)
        requires = ''.join([REQUIRE_TPL % x for x in requires + recommends])
        return requires

    def _get_requires(self, package_type):
        devel_suffix = ''
        if package_type == PackageType.DEVEL:
            devel_suffix = '-devel'
        deps = self.get_requires(package_type, devel_suffix)
        return reduce(lambda x, y: x + REQUIRE_TPL % y, deps, '')

    def _files_list(self, package_type):
        if isinstance(self.package, MetaPackage):
            return ''
        files = self.files_list(package_type)
        for f in [x for x in files if x.endswith('.py')]:
            if f + 'c' not in files:
                files.append(f + 'c')
            if f + 'o' not in files:
                files.append(f + 'o')
        return '\n'.join([os.path.join('%{prefix}',  x) for x in files])

    def _devel_package_and_files(self):
        args = {}
        args['summary'] = 'Development files for %s' % self.package.name
        args['description'] = args['summary']
        if isinstance(self.package, MetaPackage):
            args['requires'] = self._get_meta_requires(PackageType.DEVEL)
        else:
            args['requires'] = self._get_requires(PackageType.DEVEL)
        args['name'] = self.package.name
        args['p_prefix'] = self.package_prefix
        try:
            devel = DEVEL_TPL % self._files_list(PackageType.DEVEL)
        except EmptyPackageError:
            devel = ''
        return DEVEL_PACKAGE_TPL % args, devel


class Packager(object):

    def __new__(klass, config, package, store):
        return RPMPackager(config, package, store)


def register():
    from cerbero.packages.packager import register_packager
    from cerbero.config import Distro
    register_packager(Distro.REDHAT, Packager)
    register_packager(Distro.SUSE, Packager)
