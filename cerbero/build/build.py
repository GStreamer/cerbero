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
from cerbero.utils import shell, to_unixpath


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


class CustomBuild(Build):

    def configure(self):
        pass

    def compile(self):
        pass

    def install(self):
        pass


def system_libs(func):
    ''' Decorator to use system libs'''
    def call(*args):
        self = args[0]
        if self.use_system_libs and self.config.allow_system_libs:
            self._add_system_libs()
        res = func(*args)
        if self.use_system_libs and self.config.allow_system_libs:
            self._restore_pkg_config_path()
        return res

    call.func_name = func.func_name
    return call


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
    allow_parallel_build = True
    srcdir = '.'

    def __init__(self):
        self._with_system_libs = False
        Build.__init__(self)
        self.make_dir = os.path.abspath(os.path.join(self.build_dir,
                                                     self.srcdir))
        if self.config.allow_parallel_build and self.allow_parallel_build \
                and self.config.num_of_cpus > 1:
            self.make += ' -j%d' % self.config.num_of_cpus

    @system_libs
    def configure(self):
        shell.call(self.configure_tpl % {'config-sh': self.config_sh,
                                          'prefix': to_unixpath(self.config.prefix),
                                          'libdir': to_unixpath(self.config.libdir),
                                          'host': self.config.host,
                                          'target': self.config.target,
                                          'build': self.config.build,
                                          'options': self.configure_options},
                    self.make_dir)

    @system_libs
    def compile(self):
        shell.call(self.make, self.make_dir)

    @system_libs
    def install(self):
        shell.call(self.make_install, self.make_dir)

    @system_libs
    def clean(self):
        shell.call(self.make_clean, self.make_dir)

    @system_libs
    def check(self):
        if self.make_check:
            shell.call(self.make_check, self.build_dir)

    def _add_system_libs(self):
        if self._with_system_libs:
            # Don't mess the env too much
            return
        self.pkgconfiglibdir = os.environ['PKG_CONFIG_LIBDIR']
        self.pkgconfigpath = os.environ['PKG_CONFIG_PATH']
        os.environ['PKG_CONFIG_PATH'] = '%s:%s' % (self.pkgconfigpath,
                                                   self.pkgconfiglibdir)
        del os.environ['PKG_CONFIG_LIBDIR']
        self._with_system_libs = True

    def _restore_pkg_config_path(self):
        os.environ['PKG_CONFIG_PATH'] = self.pkgconfigpath
        os.environ['PKG_CONFIG_LIBDIR'] = self.pkgconfiglibdir
        self._with_system_libs = False


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
    can_use_configure_cache = True
    supports_cache_variables = True

    def configure(self):
        if self.supports_non_src_build:
            self.config_sh = os.path.join(self.repo_dir, self.config_sh)
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

        if self.config.platform == Platform.WINDOWS and \
                self.supports_cache_variables:
            # On windows, environment variables are upperscase, but we still
            # need to pass things like am_cv_python_platform in lowercase for
            # configure and autogen.sh
            for k, v in os.environ.iteritems():
                if k[2:6] == '_cv_':
                    self.configure_tpl += ' %s="%s"' % (k, v)

        if self.add_host_build_target:
            if self.config.host is not None:
                self.configure_tpl += ' --host=%(host)s'
            if self.config.build is not None:
                self.configure_tpl += ' --build=%(build)s'
            if self.config.target is not None:
                self.configure_tpl += ' --target=%(target)s'


        use_configure_cache = self.config.use_configure_cache
        if self.use_system_libs and self.config.allow_system_libs:
            use_configure_cache = False

        if use_configure_cache and self.can_use_configure_cache:
            cache = os.path.join(self.config.prefix, '.configure.cache')
            self.config_sh += ' --cache-file=%s' % cache

        MakefilesBase.configure(self)


class CMake (MakefilesBase):
    '''
    Build handler for cmake projects
    '''

    config_sh = 'cmake'
    configure_tpl = '%(config-sh)s -DCMAKE_INSTALL_PREFIX=%(prefix)s '\
                    '-DCMAKE_LIBRARY_OUTPUT_PATH=%(libdir)s %(options)s '\
                    '-DCMAKE_BUILD_TYPE=Release '\
                    '-DCMAKE_FIND_ROOT_PATH=$CERBERO_PREFIX '

    def __init__(self):
        MakefilesBase.__init__(self)

        cc = os.environ.get('CC', 'gcc')
        cxx = os.environ.get('CXX', 'g++')
        # FIXME: CMake doesn't support passing "ccache $CC"
        if self.config.use_ccache:
            cc = cc.replace('ccache ', '')
            cxx = cxx.replace('ccache ', '')

        if self.config.target_platform == Platform.WINDOWS:
            self.configure_options += ' -DCMAKE_C_COMPILER=%s '\
                                      ' -DCMAKE_CXX_COMPILER=%s '\
                                      ' -DCMAKE_SYSTEM_NAME=Windows '\
                                      % (cc, cxx)
        if self.config.platform == Platform.WINDOWS:
            self.configure_options += ' -G\\"Unix Makefiles\\"'
        self.configure_options += ' -DLIB_SUFFIX=%s ' % self.config.lib_suffix


class BuildType (object):

    CUSTOM = CustomBuild
    MAKEFILE = MakefilesBase
    AUTOTOOLS = Autotools
    CMAKE = CMake
