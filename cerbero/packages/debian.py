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

from cerbero.config import Architecture
from cerbero.errors import FatalError, EmptyPackageError
from cerbero.packages import PackagerBase, PackageType
from cerbero.packages.disttarball import DistTarball
from cerbero.packages.package import MetaPackage
from cerbero.utils import shell, _
from cerbero.utils import messages as m

CHANGELOG_TPL = \
'''%(name)s (%(version)s-0) unstable; urgency=low

  * Release %(version)s
  %(changelog_url)s

 -- %(packager)s  %(datetime)s
'''

COMPAT_TPL = '''7'''

CONTROL_TPL = \
'''Source: %(name)s
Priority: extra
Maintainer: %(packager)s
Build-Depends: debhelper
Standards-Version: 3.8.4
Section: libs
%(homepage)s

Package: %(name)s
Section: libs
Architecture: any
Depends: ${shlibs:Depends}, ${misc:Depends} %(requires)s
Description: %(shortdesc)s
 %(longdesc)s

'''

CONTROL_DBG_PACKAGE_TPL = \
'''Package: %(name)s-dbg
Section: debug
Architecture: any
Depends: %(name)s (= ${binary:Version})
Description: Debug symbols for %(name)s
 Debug symbols for %(name)s

'''

CONTROL_DEVEL_PACKAGE_TPL = \
'''Package: %(name)s-dev
Section: libdevel
Architecture: any
Depends: %(name)s (= ${binary:Version}), ${shlibs:Depends}, ${misc:Depends} %(requires)s
Description: %(shortdesc)s
 %(longdesc)s
'''

COPYRIGHT_TPL = \
'''This package was debianized by %(packager)s on
%(datetime)s.

License:

    %(licenses)s

On Debian systems, the complete text of the license(s) can be found in
%(licenses_locations)s.

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
DH_STRIP_TPL = 'dh_strip -a --dbg-package=%(name)s-dbg'

class DebianPackage(PackagerBase):

    def __init__(self, config, package, store):
        PackagerBase.__init__(self, config, package, store)
        self.full_package_name = '%s-%s' % (self.package.name, self.package.version)

    def pack(self, output_dir, devel=True, force=False,
             pack_deps=True, tmpdir=None):
        self.install_dir = self.package.get_install_dir()
        self.devel = devel
        self.force = force
        self._empty_packages = []

        d = datetime.utcnow()
        self.datetime = d.strftime("%a, %d %b %Y %H:%M:%S +0000")

        # Create a tmpdir for packages
        tmpdir, debdir, srcdir = self._create_debian_tree(tmpdir)

        # only build each package once
        if pack_deps:
            self._pack_deps(output_dir, tmpdir, force)

        if not isinstance(self.package, MetaPackage):
            # create a tarball with all the package's files
            tarball_packager = DistTarball(self.config, self.package,
                                           self.store)
            tarball = tarball_packager.pack(tmpdir, devel, True,
                    split=False, package_prefix=self.full_package_name)[0]
            tarname = os.path.join(tmpdir, os.path.split(tarball)[1])
        else:
            # metapackages only contains Requires dependencies with other packages
            tarname = None

        m.action(_("Creating debian package for %s") % self.package.name)

        self._pack(tmpdir, debdir, srcdir)

        # and build the package
        self._build(tarname, tmpdir, debdir, srcdir)

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

    def _pack_deps(self, output_dir, tmpdir, force):
        for p in self.store.get_package_deps(self.package.name):
            stamp_path = os.path.join(tmpdir, p.name + '-stamp')
            if os.path.exists(stamp_path):
                # already built, skipping
                continue

            m.action(_("Packing dependency %s for package %s") % (p.name, self.package.name))
            packager = DebianPackage(self.config, p, self.store)
            try:
                packager.pack(output_dir, self.devel, force, True, tmpdir)
            except EmptyPackageError:
                self._empty_packages.append(p.name)

    def _build(self, tarname, tmpdir, debdir, srcdir):
        if self.config.target_arch == Architecture.X86:
            target = 'i686-redhat-linux'
        elif self.config.target_arch == Architecture.X86_64:
            target = 'x86_64-redhat-linux'
        else:
            raise FatalError(_('Architecture %s not supported') % \
                             self.config.target_arch)

        if tarname:
            tar = tarfile.open(tarname, "r:bz2")
            tar.extractall(tmpdir)
            tar.close()

        if not isinstance(self.package, MetaPackage):
            # for each dependency, copy the generated shlibs to this package debian/shlibs.local,
            # so that dpkg-shlibdeps knows where our dependencies are without using Build-Depends:
            package_deps = self.store.get_package_deps(self.package.name, recursive=True)
            if package_deps:
                shlibs_local_path = os.path.join(debdir, 'shlibs.local')
                f = open(shlibs_local_path, 'w')
                for p in package_deps:
                    package_shlibs_path = os.path.join(tmpdir, p.name + '-shlibs')
                    m.action(_('Copying generated shlibs file %s for dependency %s to %s') %
                             (package_shlibs_path, p.name, shlibs_local_path))
                    shutil.copyfileobj(open(package_shlibs_path, 'r'), f)
                f.close()

        saved_path = os.getcwd()
        os.chdir(srcdir)

        shell.call('dpkg-buildpackage -rfakeroot -us -uc -D -b')

        # we may only have a generated shlibs file if at least we have runtime files
        if tarname:
            # copy generated shlibs to tmpdir/$package-shlibs to be used by dependent packages
            shlibs_path = os.path.join(debdir, self.package.name, 'DEBIAN', 'shlibs')
            out_shlibs_path = os.path.join(tmpdir, self.package.name + '-shlibs')
            m.action(_('Copying generated shlibs file %s to %s') % (shlibs_path, out_shlibs_path))
            if os.path.exists(shlibs_path):
                shutil.copy(shlibs_path, out_shlibs_path)

        stamp_path = os.path.join(tmpdir, self.package.name + '-stamp')
        open(stamp_path, 'w').close()
        os.chdir(saved_path)

    def _create_debian_tree(self, tmpdir):
        # create a tmp dir to use as topdir
        if tmpdir is None:
            tmpdir = tempfile.mkdtemp()
        srcdir = os.path.join(tmpdir, self.full_package_name)
        os.mkdir(srcdir)
        debdir = os.path.join(srcdir, 'debian')
        os.mkdir(debdir)
        os.mkdir(os.path.join(debdir, 'source'))
        m.action(_("Creating debian package structure at %s for package %s") %
                   (srcdir, self.package.name))
        return (tmpdir, debdir, srcdir)

    def _write_debian_file(self, debdir, filename, content):
        path = os.path.join(debdir, filename)
        with open(path, 'w') as f:
            f.write(content)

    def _deb_changelog(self):
        args = {}
        args['name'] = self.package.name
        # FIXME - use self.package.packager when available
        args['packager'] = 'Andre Moreira Magalhaes <andre.magalhaes@collabora.co.uk>'
        args['version'] = self.package.version
        args['datetime'] = self.datetime
        args['changelog_url'] = CHANGELOG_URL_TPL % self.package.url if self.package.url != 'default' else ''
        return CHANGELOG_TPL % args

    def _deb_control_runtime_and_files(self):
        args = {}
        args['name'] = self.package.name
        # FIXME - use self.package.packager when available
        args['packager'] = 'Andre Moreira Magalhaes <andre.magalhaes@collabora.co.uk>'
        args['homepage'] = 'Homepage: ' + self.package.url if self.package.url != 'default' else ''
        args['shortdesc'] = self.package.shortdesc
        args['longdesc'] = self.package.longdesc if self.package.longdesc != 'default' else args['shortdesc']
        requires = self._get_requires(PackageType.RUNTIME)
        args['requires'] = ', ' + requires if requires else ''
        runtime_files = self.files_list(PackageType.RUNTIME)
        if isinstance(self.package, MetaPackage):
            return CONTROL_TPL % args, runtime_files
        else:
            return (CONTROL_TPL + CONTROL_DBG_PACKAGE_TPL) % args, runtime_files

    def _deb_control_devel_and_files(self):
        args = {}
        args['name'] = self.package.name
        args['shortdesc'] = 'Development files for %s' % self.package.name
        args['longdesc'] = args['shortdesc']
        requires = self._get_requires(PackageType.DEVEL)
        args['requires'] = ', ' + requires if requires else ''
        try:
            devel_files = self.files_list(PackageType.DEVEL)
        except EmptyPackageError:
            devel_files = ''
        if devel_files:
            return CONTROL_DEVEL_PACKAGE_TPL % args, devel_files
        return '', ''

    def _deb_copyright(self):
        args = {}
        # FIXME - use self.package.packager when available
        args['packager'] = 'Andre Moreira Magalhaes <andre.magalhaes@collabora.co.uk>'
        args['datetime'] = self.datetime
        args['licenses'] = ' '.join(self.package.licenses)
        args['licenses_locations'] = ', '.join(['/usr/share/common-licenses/' + l for l in self.package.licenses])
        return COPYRIGHT_TPL % args

    def _deb_rules(self):
        args = {}
        args['name'] = self.package.name
        if not isinstance(self.package, MetaPackage):
            args['dh_strip'] = DH_STRIP_TPL % args
        else:
            args['dh_strip'] = ''
        return RULES_TPL % args

    def _pack(self, tmpdir, debdir, srcdir):
        changelog = self._deb_changelog()
        compat = COMPAT_TPL

        control, runtime_files = self._deb_control_runtime_and_files()

        if self.devel:
            control_devel, devel_files = self._deb_control_devel_and_files()
        else:
            control_devel, devel_files = '', ''

        self.package.has_devel_package = bool(devel_files)

        copyright = self._deb_copyright()

        rules = self._deb_rules()
        source_format = SOURCE_FORMAT_TPL

        self._write_debian_file(debdir, 'changelog', changelog)
        self._write_debian_file(debdir, 'compat', compat)
        self._write_debian_file(debdir, 'control', control + control_devel)
        self._write_debian_file(debdir, 'copyright', copyright)
        self._write_debian_file(debdir, 'rules', rules)
        self._write_debian_file(debdir, os.path.join('source', 'format'), source_format)
        self._write_debian_file(debdir, self.package.name + '.install', runtime_files)
        if self.devel and devel_files:
            self._write_debian_file(debdir, self.package.name + '-dev.install', devel_files)

    def _get_requires(self, package_type):
        deps = [p.name for p in self.store.get_package_deps(self.package.name)]
        deps = list(set(deps) - set(self._empty_packages))
        if package_type == PackageType.DEVEL:
            deps = [x for x in deps if self.store.get_package(x).has_devel_package]
            deps = map(lambda x: x+'-dev', deps)
        return ', '.join(deps)

    def files_list(self, package_type):
        # metapackages only have dependencies in other packages
        if isinstance(self.package, MetaPackage):
            return ''
        files = PackagerBase.files_list(self, package_type, self.force)
        return '\n'.join([f + ' ' + os.path.join(self.install_dir.lstrip('/'),
                          os.path.dirname(f)) for f in files])


class Packager(object):

    def __new__(klass, config, package, store):
        return DebianPackage(config, package, store)


def register():
    from cerbero.packages.packager import register_packager
    from cerbero.config import Distro
    register_packager(Distro.DEBIAN, Packager)
