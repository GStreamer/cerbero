# cerbero - a multi-platform build system for Open Source software
# Copyright (C) 2012 Collabora Ltd. <http://www.collabora.co.uk/>
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
import tarfile
import tempfile

from datetime import datetime
from fnmatch import fnmatch

from cerbero.errors import EmptyPackageError
from cerbero.packages import PackageType
from cerbero.packages.linux import LinuxPackager
from cerbero.packages.package import MetaPackage, App
from cerbero.utils import shell, _
from cerbero.utils import messages as m

CHANGELOG_TPL = \
'''%(p_prefix)s%(name)s (%(version)s-1) unstable; urgency=low

  * Release %(version)s
  %(changelog_url)s

 -- %(packager)s  %(datetime)s
'''

COMPAT_TPL = '''7'''

CONTROL_TPL = \
'''Source: %(p_prefix)s%(name)s
Priority: extra
Maintainer: %(packager)s
Build-Depends: debhelper
Standards-Version: 3.8.4
Section: libs
%(homepage)s

'''

CONTROL_RUNTIME_PACKAGE_TPL = \
'''Package: %(p_prefix)s%(name)s
Section: libs
Architecture: any
Depends: ${shlibs:Depends}, ${misc:Depends} %(requires)s
Recommends: %(recommends)s
Suggests: %(suggests)s
Description: %(shortdesc)s
 %(longdesc)s

'''

CONTROL_DBG_PACKAGE_TPL = \
'''Package: %(p_prefix)s%(name)s-dbg
Section: debug
Architecture: any
Depends: %(p_prefix)s%(name)s (= ${binary:Version})
Description: Debug symbols for %(p_prefix)s%(name)s
 Debug symbols for %(p_prefix)s%(name)s

'''

CONTROL_DEVEL_PACKAGE_TPL = \
'''Package: %(p_prefix)s%(name)s-dev
Section: libdevel
Architecture: any
Depends: ${shlibs:Depends}, ${misc:Depends} %(requires)s
Recommends: %(recommends)s
Suggests: %(suggests)s
Description: %(shortdesc)s
 %(longdesc)s
'''

COPYRIGHT_TPL = \
'''This package was debianized by %(packager)s on
%(datetime)s.

%(license_notes)s

License:

    This packaging is licensed under %(license)s, and includes files from the
    following licenses:
    %(recipes_licenses)s

On Debian systems, the complete text of common license(s) can be found in
/usr/share/common-licenses/.

'''

COPYRIGHT_TPL_META = \
'''This package was debianized by %(packager)s on
%(datetime)s.

%(license_notes)s

License:

    This packaging is licensed under %(license)s.

On Debian systems, the complete text of common license(s) can be found in
/usr/share/common-licenses/.

'''

RULES_TPL = \
'''#!/usr/bin/make -f

# Uncomment this to turn on verbose mode.
#export DH_VERBOSE=1

build: build-stamp
build-stamp:
	dh_testdir
	touch build-stamp

clean:
	dh_testdir
	dh_testroot
	rm -f build-stamp
	dh_clean

install: build
	dh_testdir
	dh_testroot
	dh_prep
	dh_installdirs
	dh_installdocs
	dh_install

# Build architecture-independent files here.
binary-indep: build install
# We have nothing to do by default.

# Build architecture-dependent files here.
binary-arch: build install
	dh_testdir -a
	dh_testroot -a
	%(dh_strip)s
	dh_link -a
	dh_compress -a
	dh_fixperms -a
	dh_makeshlibs -a -V
	dh_installdeb -a
	dh_shlibdeps -a
	dh_gencontrol -a
	dh_md5sums -a
	dh_builddeb -a

binary: binary-indep binary-arch
.PHONY: build clean binary-indep binary-arch binary install
'''

SOURCE_FORMAT_TPL = '''3.0 (native)'''

CHANGELOG_URL_TPL = '* Full changelog can be found at %s'
DH_STRIP_TPL = 'dh_strip -a --dbg-package=%(p_prefix)s%(name)s-dbg %(excl)s'


class DebianPackager(LinuxPackager):
    LICENSE_TXT = 'license.txt'

    def __init__(self, config, package, store):
        LinuxPackager.__init__(self, config, package, store)

        d = datetime.utcnow()
        self.datetime = d.strftime('%a, %d %b %Y %H:%M:%S +0000')

        license_path = self.package.relative_path(self.LICENSE_TXT)
        if os.path.exists(license_path):
            with open(license_path, 'r') as f:
                self.license = f.read()
        else:
            self.license = ''

    def create_tree(self, tmpdir):
        # create a tmp dir to use as topdir
        if tmpdir is None:
            tmpdir = tempfile.mkdtemp()
        srcdir = os.path.join(tmpdir, self.full_package_name)
        os.mkdir(srcdir)
        packagedir = os.path.join(srcdir, 'debian')
        os.mkdir(packagedir)
        os.mkdir(os.path.join(packagedir, 'source'))
        m.action(_('Creating debian package structure at %s for package %s') %
                (srcdir, self.package.name))
        if os.path.exists(self.package.resources_postinstall):
            shutil.copy(os.path.join(self.package.resources_postinstall),
                        os.path.join(packagedir, 'postinst'))
        if os.path.exists(self.package.resources_postremove):
            shutil.copy(os.path.join(self.package.resources_postremove),
                        os.path.join(packagedir, 'postrm'))
        return (tmpdir, packagedir, srcdir)

    def setup_source(self, tarball, tmpdir, packagedir, srcdir):
        tarname = os.path.join(tmpdir, os.path.split(tarball)[1])
        return tarname

    def prepare(self, tarname, tmpdir, packagedir, srcdir):
        changelog = self._deb_changelog()
        compat = COMPAT_TPL

        control, runtime_files = self._deb_control_runtime_and_files()

        if len(runtime_files) != 0 or isinstance(self.package, MetaPackage):
            self.package.has_runtime_package = True
        else:
            self.package.has_runtime_package = False

        if self.devel:
            control_devel, devel_files = self._deb_control_devel_and_files()
        else:
            control_devel, devel_files = '', ''

        if len(devel_files) != 0 or isinstance(self.package, MetaPackage):
            self.package.has_devel_package = True
        else:
            self.package.has_devel_package = False

        copyright = self._deb_copyright()

        rules = self._deb_rules()
        source_format = SOURCE_FORMAT_TPL

        self._write_debian_file(packagedir, 'changelog', changelog)
        self._write_debian_file(packagedir, 'compat', compat)
        self._write_debian_file(packagedir, 'control', control + control_devel)
        self._write_debian_file(packagedir, 'copyright', copyright)
        rules_path = self._write_debian_file(packagedir, 'rules', rules)
        os.chmod(rules_path, 0755)
        self._write_debian_file(packagedir, os.path.join('source', 'format'),
                source_format)
        if self.package.has_runtime_package:
            self._write_debian_file(packagedir,
                    self.package_prefix + self.package.name + '.install',
                    runtime_files)
        if self.devel and self.package.has_devel_package:
            self._write_debian_file(packagedir,
                    self.package_prefix + self.package.name + '-dev.install',
                    devel_files)

    def build(self, output_dir, tarname, tmpdir, packagedir, srcdir):
        if tarname:
            tar = tarfile.open(tarname, 'r:bz2')
            tar.extractall(tmpdir)
            tar.close()

        if not isinstance(self.package, MetaPackage):
            # for each dependency, copy the generated shlibs to this
            # package debian/shlibs.local, so that dpkg-shlibdeps knows where
            # our dependencies are without using Build-Depends:
            package_deps = self.store.get_package_deps(self.package.name,
                    recursive=True)
            if package_deps:
                shlibs_local_path = os.path.join(packagedir, 'shlibs.local')
                f = open(shlibs_local_path, 'w')
                for p in package_deps:
                    package_shlibs_path = os.path.join(tmpdir,
                            self.package_prefix + p.name + '-shlibs')
                    m.action(_('Copying generated shlibs file %s for ' \
                            'dependency %s to %s') %
                            (package_shlibs_path, p.name, shlibs_local_path))
                    if os.path.exists(package_shlibs_path):
                        shutil.copyfileobj(open(package_shlibs_path, 'r'), f)
                f.close()

        shell.call('dpkg-buildpackage -rfakeroot -us -uc -D -b', srcdir)

        # we may only have a generated shlibs file if at least we have
        # runtime files
        if tarname:
            # copy generated shlibs to tmpdir/$package-shlibs to be used by
            # dependent packages
            shlibs_path = os.path.join(packagedir,
                    self.package_prefix + self.package.name,
                    'DEBIAN', 'shlibs')
            out_shlibs_path = os.path.join(tmpdir,
                    self.package_prefix + self.package.name + '-shlibs')
            m.action(_('Copying generated shlibs file %s to %s') %
                    (shlibs_path, out_shlibs_path))
            if os.path.exists(shlibs_path):
                shutil.copy(shlibs_path, out_shlibs_path)

        # copy the newly created package, which should be in tmpdir
        # to the output dir
        paths = []
        for f in os.listdir(tmpdir):
            if fnmatch(f, '*.deb'):
                out_path = os.path.join(output_dir, f)
                if os.path.exists(out_path):
                    os.remove(out_path)
                paths.append(out_path)
                shutil.move(os.path.join(tmpdir, f), output_dir)
        return paths

    def _get_requires(self, package_type):
        devel_suffix = ''
        if package_type == PackageType.DEVEL:
            devel_suffix = '-dev'
        deps = self.get_requires(package_type, devel_suffix)
        return ', '.join(deps)

    def _files_list(self, package_type):
        # metapackages only have dependencies in other packages
        if isinstance(self.package, MetaPackage):
            return ''
        files = self.files_list(package_type)
        return '\n'.join([f + ' ' + os.path.join(self.install_dir.lstrip('/'),
                    os.path.dirname(f)) for f in files])

    def _write_debian_file(self, packagedir, filename, content):
        path = os.path.join(packagedir, filename)
        with open(path, 'w') as f:
            f.write(content)
        return path

    def _deb_changelog(self):
        args = {}
        args['name'] = self.package.name
        args['p_prefix'] = self.package_prefix
        args['packager'] = self.packager
        args['version'] = self.package.version
        args['datetime'] = self.datetime
        args['changelog_url'] = CHANGELOG_URL_TPL % self.package.url \
                if self.package.url != 'default' else ''
        return CHANGELOG_TPL % args

    def _deb_control_runtime_and_files(self):
        args = {}
        args['name'] = self.package.name
        args['p_prefix'] = self.package_prefix
        args['packager'] = self.packager
        args['homepage'] = 'Homepage: ' + self.package.url \
                if self.package.url != 'default' else ''
        args['shortdesc'] = self.package.shortdesc
        args['longdesc'] = self.package.longdesc \
                if self.package.longdesc != 'default' else args['shortdesc']

        try:
            runtime_files = self._files_list(PackageType.RUNTIME)
        except EmptyPackageError:
            runtime_files = ''

        if isinstance(self.package, MetaPackage):
            requires, recommends, suggests = \
                    self.get_meta_requires(PackageType.RUNTIME, '')
            requires = ', '.join(requires)
            recommends = ', '.join(recommends)
            suggests = ', '.join(suggests)
            args['requires'] = ', ' + requires if requires else ''
            args['recommends'] = recommends
            args['suggests'] = suggests
            return (CONTROL_TPL + CONTROL_RUNTIME_PACKAGE_TPL) % args, runtime_files

        requires = self._get_requires(PackageType.RUNTIME)
        args['requires'] = ', ' + requires if requires else ''
        args['recommends'] = ''
        args['suggests'] = ''
        if runtime_files:
            return (CONTROL_TPL + CONTROL_RUNTIME_PACKAGE_TPL + CONTROL_DBG_PACKAGE_TPL) % \
                    args, runtime_files
        return CONTROL_TPL % args, ''

    def _deb_control_devel_and_files(self):
        args = {}
        args['name'] = self.package.name
        args['p_prefix'] = self.package_prefix
        args['shortdesc'] = 'Development files for %s' % \
                self.package_prefix + self.package.name
        args['longdesc'] = args['shortdesc']

        try:
            devel_files = self._files_list(PackageType.DEVEL)
        except EmptyPackageError:
            devel_files = ''

        if isinstance(self.package, MetaPackage):
            requires, recommends, suggests = \
                self.get_meta_requires(PackageType.DEVEL, '-dev')
            requires = ', '.join(requires)
            recommends = ', '.join(recommends)
            suggests = ', '.join(suggests)
            args['requires'] = ', ' + requires if requires else ''
            args['recommends'] = recommends
            args['suggests'] = suggests
            return CONTROL_DEVEL_PACKAGE_TPL % args, devel_files

        requires = self._get_requires(PackageType.DEVEL)
        args['requires'] = ', ' + requires if requires else ''
        if self.package.has_runtime_package:
            args['requires'] += (', %(p_prefix)s%(name)s (= ${binary:Version})' % args)
        args['recommends'] = ''
        args['suggests'] = ''
        if devel_files:
            return CONTROL_DEVEL_PACKAGE_TPL % args, devel_files
        return '', ''

    def _deb_copyright(self):
        args = {}
        args['packager'] = self.packager
        args['datetime'] = self.datetime
        args['license'] = self.license

        args['license_notes'] = self.license
        args['license'] = self.package.license.pretty_name

        if isinstance(self.package, MetaPackage):
            return COPYRIGHT_TPL_META % args

        args['recipes_licenses'] = ',\n    '.join(
                [l.pretty_name for l in self.recipes_licenses()])
        return COPYRIGHT_TPL % args

    def _deb_rules(self):
        args = {}
        args['name'] = self.package.name
        args['p_prefix'] = self.package_prefix
        args['excl'] = ''
        if isinstance(self.package, App):
            args['excl'] =  ' '.join(['-X%s' % x for x in
                self.package.strip_excludes])
        if not isinstance(self.package, MetaPackage) and \
           self.package.has_runtime_package:
            args['dh_strip'] = DH_STRIP_TPL % args
        else:
            args['dh_strip'] = ''
        return RULES_TPL % args


class Packager(object):

    def __new__(klass, config, package, store):
        return DebianPackager(config, package, store)


def register():
    from cerbero.packages.packager import register_packager
    from cerbero.config import Distro
    register_packager(Distro.DEBIAN, Packager)
