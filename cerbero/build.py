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

from cerbero.config import Platform
from cerbero.utils import shell


class Build (object):
    '''
    Base class for build handlers

    @ivar recipe: the parent recipe
    @type recipe: L{cerbero.recipe.Recipe}
    @ivar config: cerbero's configuration
    @type config: L{cerbero.config.Config}
    '''

    _properties_keys = []

    def configure(self):
        '''
        Configures the module
        '''
        raise NotImplemented("'configure' must be implemented by subclasses")

    def compile(self):
        '''
        Compiles the module
        '''
        raise NotImplemented("'make' must be implemented by subclasses")

    def install(self):
        '''
        Installs the module
        '''
        raise NotImplemented("'install' must be implemented by subclasses")

    def check(self):
        '''
        Runs any checks on the module
        '''
        pass


class MakefilesBase (Build):
    '''
    Base class for makefiles build systems like autotools and cmake
    '''

    config_sh = ''
    configure_tpl = ''
    configure_options = ''
    force_configure = False
    make = 'make'
    make_install = 'make install'
    make_check = None
    make_clean = 'make clean'
    use_system_libs = False
    srcdir = '.'

    def __init__(self):
        Build.__init__(self)
        self.make_dir = os.path.abspath(os.path.join(self.build_dir,
                                                     self.srcdir))

    def configure(self):
        self._add_system_libs()
        shell.call(self.configure_tpl % {'config-sh': self.config_sh,
                                          'prefix': self.config.prefix,
                                          'libdir': self.config.libdir,
                                          'host': self.config.host,
                                          'target': self.config.target,
                                          'build': self.config.build,
                                          'options': self.configure_options},
                    self.make_dir)
        self._restore_pkg_config_path()

    def compile(self):
        self._add_system_libs()
        shell.call(self.make, self.make_dir)
        self._restore_pkg_config_path()

    def install(self):
        self._add_system_libs()
        shell.call(self.make_install, self.make_dir)
        self._restore_pkg_config_path()

    def clean(self):
        shell.call(self.make_clean, self.make_dir)

    def check(self):
        if self.make_check:
            shell.call(self.make_check, self.build_dir)

    def _add_system_libs(self):
        if self.use_system_libs:
            self.pkgconfiglibdir = os.environ['PKG_CONFIG_LIBDIR']
            self.pkgconfigpath = os.environ['PKG_CONFIG_PATH']
            os.environ['PKG_CONFIG_PATH'] = '%s:%s' % (self.pkgconfigpath,
                                                       self.pkgconfiglibdir)
            del os.environ['PKG_CONFIG_LIBDIR']

    def _restore_pkg_config_path(self):
        if self.use_system_libs:
            os.environ['PKG_CONFIG_PATH'] = self.pkgconfigpath
            os.environ['PKG_CONFIG_LIBDIR'] = self.pkgconfiglibdir


class Autotools (MakefilesBase):
    '''
    Build handler for autotools project
    '''

    autoreconf = False
    autoreconf_sh = 'autoreconf -f -i'
    config_sh = './configure'
    configure_tpl = "%(config-sh)s --prefix %(prefix)s "\
                    "--libdir %(libdir)s %(options)s"
    make_check = 'make check'
    add_host_build_target = True

    def configure(self):
        # skip configure if we are already configured
        if os.path.exists(os.path.join(self.make_dir, 'configure')) and\
                os.path.exists(os.path.join(self.make_dir, 'Makefile')):
            if not self.force_configure and not self.force:
                return

        # Only use --disable-maintainer mode for real autotools based projects
        if os.path.exists(os.path.join(self.make_dir, 'configure.in')) or\
                os.path.exists(os.path.join(self.make_dir, 'configure.ac')):
            self.configure_tpl += " --disable-maintainer-mode"

        if self.autoreconf:
            shell.call(self.autoreconf_sh, self.make_dir)

        if self.config.platform == Platform.WINDOWS:
            # On windows, environment variables are upperscase, but we still
            # need to pass things like am_cv_python_platform in lowercase for
            # configure and autogen.sh
            for k, v in os.environ.iteritems():
                if k.islower():
                    self.configure_tpl += ' %s="%s"' % (k, v)

        if self.add_host_build_target:
            if self.config.host is not None:
                self.configure_tpl += ' --host=%(host)s'
            if self.config.build is not None:
                self.configure_tpl += ' --build=%(build)s'
            if self.config.target is not None:
                self.configure_tpl += ' --target=%(target)s'
        MakefilesBase.configure(self)


class CMake (MakefilesBase):
    '''
    Build handler for cmake projects
    '''

    config_sh = 'cmake'
    configure_tpl = '%(config-sh)s -DCMAKE_INSTALL_PREFIX=%(prefix)s '\
                    '-DCMAKE_BUILD_TYPE=Release '\
                    '-DCMAKE_LIBRARY_OUTPUT_PATH=%(libdir)s %(options)s'
    configure_options = ''


class BuildType (object):

    AUTOTOOLS = Autotools
    CMAKE = CMake
