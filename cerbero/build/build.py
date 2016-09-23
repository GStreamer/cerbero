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
import re
import copy
import shutil
import shlex
import sysconfig

from cerbero.config import Platform, Architecture, Distro
from cerbero.utils import shell, to_unixpath, add_system_libs
from cerbero.utils import messages as m


class Build (object):
    '''
    Base class for build handlers

    @ivar recipe: the parent recipe
    @type recipe: L{cerbero.recipe.Recipe}
    @ivar config: cerbero's configuration
    @type config: L{cerbero.config.Config}
    '''

    # Whether this recipe's build system can be built with MSVC
    can_msvc = False
    _properties_keys = []

    def using_msvc(self):
        if not self.can_msvc:
            return False
        if not self.config.variants.visualstudio:
            return False
        return True

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


def modify_environment(func):
    ''' Decorator to modify the build environment '''
    def call(*args):
        self = args[0]
        append_env = self.append_env
        new_env = self.new_env.copy()
        if self.use_system_libs and self.config.allow_system_libs:
            self._add_system_libs(new_env)
        old_env = self._modify_env(append_env, new_env)
        res = func(*args)
        self._restore_env(old_env)
        return res

    call.__name__ = func.__name__
    return call


class ModifyEnvBase:
    '''
    Base class for build systems that require extra env variables
    '''

    append_env = None
    new_env = None
    use_system_libs = False

    def __init__(self):
        if self.append_env is None:
            self.append_env = {}
        if self.new_env is None:
            self.new_env = {}
        self._old_env = None

    def _modify_env(self, append_env, new_env):
        '''
        Modifies the build environment appending the values in
        append_env or replacing the values in new_env
        '''
        if self._old_env is not None:
            return None

        self._old_env = {}
        for var in list(append_env.keys()) + list(new_env.keys()):
            self._old_env[var] = os.environ.get(var, None)

        for var, val in append_env.items():
            if var not in os.environ:
                os.environ[var] = val
            else:
                os.environ[var] = '%s %s' % (os.environ[var], val)

        for var, val in new_env.items():
            if val is None:
                if var in os.environ:
                    del os.environ[var]
            else:
                os.environ[var] = val
        return self._old_env

    def _restore_env(self, old_env):
        ''' Restores the old environment '''
        if old_env is None:
            return

        for var, val in old_env.items():
            if val is None:
                if var in os.environ:
                    del os.environ[var]
            else:
                os.environ[var] = val
        self._old_env = None

    def _add_system_libs(self, new_env):
        '''
        Add /usr/lib/pkgconfig to PKG_CONFIG_PATH so the system's .pc file
        can be found.
        '''
        add_system_libs(self.config, new_env)


class MakefilesBase (Build, ModifyEnvBase):
    '''
    Base class for makefiles build systems like autotools and cmake
    '''

    config_sh = ''
    configure_tpl = ''
    configure_options = ''
    make = 'make'
    make_install = 'make install'
    make_check = None
    make_clean = 'make clean'
    allow_parallel_build = True
    srcdir = '.'
    requires_non_src_build = False

    def __init__(self):
        Build.__init__(self)
        ModifyEnvBase.__init__(self)
        self.config_src_dir = os.path.abspath(os.path.join(self.build_dir,
                                                           self.srcdir))
        if self.requires_non_src_build:
            self.make_dir = os.path.join (self.config_src_dir, "cerbero-build-dir")
        else:
            self.make_dir = self.config_src_dir
        if self.config.allow_parallel_build and self.allow_parallel_build \
                and self.config.num_of_cpus > 1:
            self.make += ' -j%d' % self.config.num_of_cpus

        # Make sure user's env doesn't mess up with our build.
        self.new_env['MAKEFLAGS'] = None

        # Disable site config, which is set on openSUSE
        self.new_env['CONFIG_SITE'] = None

    @modify_environment
    def configure(self):
        if not os.path.exists(self.make_dir):
            os.makedirs(self.make_dir)
        if self.requires_non_src_build:
            self.config_sh = os.path.join('../', self.config_sh)

        # Only add this for non-meson recipes, and only for iPhoneOS
        if self.config.ios_platform == 'iPhoneOS':
            # FIXME: this overwrites values set by the recipe
            self.append_env['CFLAGS'] = ' -fembed-bitcode '
            self.append_env['CCASFLAGS'] = ' -fembed-bitcode '
            # Autotools only adds LDFLAGS when doing compiler checks,
            # so add -fembed-bitcode again
            self.append_env['LDFLAGS'] = ' -fembed-bitcode -Wl,-bitcode_bundle '

        shell.call(self.configure_tpl % {'config-sh': self.config_sh,
            'prefix': to_unixpath(self.config.prefix),
            'libdir': to_unixpath(self.config.libdir),
            'host': self.config.host,
            'target': self.config.target,
            'build': self.config.build,
            'options': self.configure_options},
            self.make_dir)

    @modify_environment
    def compile(self):
        shell.call(self.make, self.make_dir)

    @modify_environment
    def install(self):
        shell.call(self.make_install, self.make_dir)

    @modify_environment
    def clean(self):
        shell.call(self.make_clean, self.make_dir)

    @modify_environment
    def check(self):
        if self.make_check:
            shell.call(self.make_check, self.build_dir)


class Autotools (MakefilesBase):
    '''
    Build handler for autotools project
    '''

    autoreconf = False
    autoreconf_sh = 'autoreconf -f -i'
    config_sh = './configure'
    configure_tpl = "%(config-sh)s --prefix %(prefix)s "\
                    "--libdir %(libdir)s"
    make_check = 'make check'
    add_host_build_target = True
    can_use_configure_cache = True
    supports_cache_variables = True
    disable_introspection = False

    def configure(self):
        # Only use --disable-maintainer mode for real autotools based projects
        if os.path.exists(os.path.join(self.config_src_dir, 'configure.in')) or\
                os.path.exists(os.path.join(self.config_src_dir, 'configure.ac')):
            self.configure_tpl += " --disable-maintainer-mode "
            self.configure_tpl += " --disable-silent-rules "

        if self.config.variants.gi and not self.disable_introspection:
            self.configure_tpl += " --enable-introspection "
        else:
            self.configure_tpl += " --disable-introspection "

        if self.autoreconf:
            shell.call(self.autoreconf_sh, self.config_src_dir)

        files = shell.check_call('find %s -type f -name config.guess' %
                                 self.config_src_dir).split('\n')
        files.remove('')
        for f in files:
            o = os.path.join(self.config._relative_path('data'), 'autotools',
                             'config.guess')
            m.action("copying %s to %s" % (o, f))
            shutil.copy(o, f)

        files = shell.check_call('find %s -type f -name config.sub' %
                                 self.config_src_dir).split('\n')
        files.remove('')
        for f in files:
            o = os.path.join(self.config._relative_path('data'), 'autotools',
                             'config.sub')
            m.action("copying %s to %s" % (o, f))
            shutil.copy(o, f)

        if self.config.platform == Platform.WINDOWS and \
                self.supports_cache_variables:
            # On windows, environment variables are upperscase, but we still
            # need to pass things like am_cv_python_platform in lowercase for
            # configure and autogen.sh
            for k, v in os.environ.items():
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

        if self.new_env or self.append_env:
            use_configure_cache = False

        if use_configure_cache and self.can_use_configure_cache:
            cache = os.path.join(self.config.sources, '.configure.cache')
            self.configure_tpl += ' --cache-file=%s' % cache

        # Add at the very end to allow recipes to override defaults
        self.configure_tpl += "  %(options)s "

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

    @modify_environment
    def configure(self):
        cc = os.environ.get('CC', 'gcc')
        cxx = os.environ.get('CXX', 'g++')
        cflags = os.environ.get('CFLAGS', '')
        cxxflags = os.environ.get('CXXFLAGS', '')
        # FIXME: CMake doesn't support passing "ccache $CC"
        if self.config.use_ccache:
            cc = cc.replace('ccache', '').strip()
            cxx = cxx.replace('ccache', '').strip()
        cc = cc.split(' ')[0]
        cxx = cxx.split(' ')[0]

        if self.config.target_platform == Platform.WINDOWS:
            self.configure_options += ' -DCMAKE_SYSTEM_NAME=Windows '
        elif self.config.target_platform == Platform.ANDROID:
            self.configure_options += ' -DCMAKE_SYSTEM_NAME=Linux '
        if self.config.platform == Platform.WINDOWS:
            self.configure_options += ' -G\\"Unix Makefiles\\"'

        # FIXME: Maybe export the sysroot properly instead of doing regexp magic
        if self.config.target_platform in [Platform.DARWIN, Platform.IOS]:
            r = re.compile(r".*-isysroot ([^ ]+) .*")
            sysroot = r.match(cflags).group(1)
            self.configure_options += ' -DCMAKE_OSX_SYSROOT=%s' % sysroot

        self.configure_options += ' -DCMAKE_C_COMPILER=%s ' % cc
        self.configure_options += ' -DCMAKE_CXX_COMPILER=%s ' % cxx
        self.configure_options += ' -DCMAKE_C_FLAGS="%s"' % cflags
        self.configure_options += ' -DCMAKE_CXX_FLAGS="%s"' % cxxflags
        self.configure_options += ' -DLIB_SUFFIX=%s ' % self.config.lib_suffix
        cmake_cache = os.path.join(self.build_dir, 'CMakeCache.txt')
        cmake_files = os.path.join(self.build_dir, 'CMakeFiles')
        if os.path.exists(cmake_cache):
            os.remove(cmake_cache)
        if os.path.exists(cmake_files):
            shutil.rmtree(cmake_files)
        MakefilesBase.configure(self)


MESON_CROSS_FILE_TPL = \
'''
[host_machine]
system = '{system}'
cpu_family = '{cpu}'
cpu = '{cpu}'
endian = '{endian}'

[properties]
{extra_properties}

[binaries]
c = {CC}
cpp = {CXX}
ar = {AR}
strip = {STRIP}
windres = {WINDRES}
pkgconfig = 'pkg-config'
'''

class Meson (Build, ModifyEnvBase) :
    '''
    Build handler for meson project
    '''

    make = None
    make_install = None
    make_check = None
    make_clean = None
    meson_sh = None
    meson_options = {}
    meson_cross_properties = {}
    meson_tpl = '%(meson-sh)s --prefix %(prefix)s --libdir %(libdir)s \
            --default-library=%(default-library)s --buildtype=%(buildtype)s \
            --backend=%(backend)s --wrap-mode=nodownload ..'
    meson_default_library = 'shared'
    meson_backend = 'ninja'
    # All meson recipes are MSVC-compatible, except if the code itself isn't
    can_msvc = True

    def __init__(self):
        Build.__init__(self)
        ModifyEnvBase.__init__(self)

        # Whether to reset the toolchain env vars set by the cerbero config
        # before building the recipe
        reset_toolchain_envvars = False
        if self.config.cross_compiling():
            # We export the cross toolchain with env vars, but Meson picks the
            # native toolchain from these, so unset them.
            # FIXME: https://bugzilla.gnome.org/show_bug.cgi?id=791670
            # NOTE: This means we require a native compiler on the build
            # machine when cross-compiling, which in practice is not a problem
            reset_toolchain_envvars = True
        if self.using_msvc():
            # The toolchain env vars set by us are for GCC, so unset them if
            # we're building with MSVC
            reset_toolchain_envvars = True
            # Set the MSVC toolchain environment
            self.new_env.update(self.config.msvc_toolchain_env)
        if reset_toolchain_envvars:
            # Only reset vars that are read by Meson for now
            for var in ('CC', 'CXX', 'AR', 'WINDRES', 'STRIP', 'CFLAGS',
                        'CXXFLAGS', 'LDFLAGS'):
                self.new_env[var] = None

        # Find Meson
        if not self.meson_sh:
            if self.config.platform == Platform.WINDOWS:
                meson = 'meson.py'
            else:
                meson = 'meson'
            # 'Scripts' on Windows and 'bin' on other platforms including MSYS
            bindir = sysconfig.get_path('scripts', vars={'base':''}).strip('\\/')
            meson_path = os.path.join(self.config.build_tools_prefix, bindir, meson)
            self.meson_sh = self.config.python_exe + ' ' + meson_path

        # Find ninja
        if not self.make:
            self.make = 'ninja -v'
        if not self.make_install:
            self.make_install = self.make + ' install'
        if not self.make_check:
            self.make_check = self.make + ' test'
        if not self.make_clean:
            self.make_clean = self.make + ' clean'

    def write_meson_cross_file(self):
        # Take cross toolchain from _old_env because we removed them from the
        # env so meson doesn't detect them as the native toolchain.
        # Same for *FLAGS below.
        cc = self._old_env.get('CC', '').split(' ')
        cxx = self._old_env.get('CXX', '').split(' ')
        ar = self._old_env.get('AR', '').split(' ')
        strip = self._old_env.get('STRIP', '').split(' ')
        windres = self._old_env.get('WINDRES', '').split(' ')

        # *FLAGS are only passed to the native compiler, so while
        # cross-compiling we need to pass these through the cross file.
        if isinstance(self.config.universal_archs, dict):
            # Universal builds have arch-specific prefixes inside the universal prefix
            libdir = '{}/{}/lib{}'.format(self.config.prefix, self.config.target_arch,
                                          self.config.lib_suffix)
        else:
            libdir = '{}/lib{}'.format(self.config.prefix, self.config.lib_suffix)
        c_link_args = ['-L' + libdir]
        c_link_args += shlex.split(self._old_env.get('LDFLAGS', ''))
        cpp_link_args = c_link_args
        c_args = shlex.split(self._old_env.get('CFLAGS', ''))
        cpp_args = shlex.split(self._old_env.get('CXXFLAGS', ''))

        # Operate on a copy of the recipe properties to avoid accumulating args
        # from all archs when doing universal builds
        cross_properties = copy.deepcopy(self.meson_cross_properties)
        for args in ('c_args', 'cpp_args', 'c_link_args', 'cpp_link_args'):
            if args in cross_properties:
                cross_properties[args] += locals()[args]
            else:
                cross_properties[args] = locals()[args]

        extra_properties = ''
        for k, v in cross_properties.items():
            extra_properties += '{} = {}\n'.format(k, str(v))

        # Create a cross-info file that tells Meson and GCC how to cross-compile
        # this project
        cross_file = os.path.join(self.meson_dir, 'meson-cross-file.txt')
        contents = MESON_CROSS_FILE_TPL.format(
                system=self.config.target_platform,
                cpu=self.config.target_arch,
                # Assume all ARM sub-archs are in little endian mode
                endian='little',
                CC=cc,
                CXX=cxx,
                AR=ar,
                STRIP=strip,
                WINDRES=windres,
                extra_properties=extra_properties)
        with open(cross_file, 'w') as f:
            f.write(contents)

        return cross_file

    @modify_environment
    def configure(self):
        # self.build_dir is different on each call to configure() when doing universal builds
        self.meson_dir = os.path.join(self.build_dir, "_builddir")
        if os.path.exists(self.meson_dir):
            # Only remove if it's not empty
            if os.listdir(self.meson_dir):
                shutil.rmtree(self.meson_dir)
                os.makedirs(self.meson_dir)
        else:
            os.makedirs(self.meson_dir)

        if self.config.variants.debug:
            buildtype = 'debug'
        elif self.config.variants.nodebug:
            buildtype = 'release'
        else:
            buildtype = 'debugoptimized'

        meson_cmd = self.meson_tpl % {
            'meson-sh': self.meson_sh,
            'prefix': self.config.prefix,
            'libdir': 'lib' + self.config.lib_suffix,
            'default-library': self.meson_default_library,
            'buildtype': buildtype,
            'backend': self.meson_backend }

        # Don't enable bitcode by passing flags manually, use the option
        if self.config.ios_platform == 'iPhoneOS':
            self.meson_options.update({'b_bitcode': 'true'})

        if self.config.cross_compiling():
            f = self.write_meson_cross_file()
            meson_cmd += ' --cross-file=' + f

        for (key, value) in self.meson_options.items():
            meson_cmd += ' -D%s=%s' % (key, str(value))

        shell.call(meson_cmd, self.meson_dir)

    @modify_environment
    def compile(self):
        shell.call(self.make, self.meson_dir)

    @modify_environment
    def install(self):
        shell.call(self.make_install, self.meson_dir)

    @modify_environment
    def clean(self):
        shell.call(self.make_clean, self.meson_dir)

    @modify_environment
    def check(self):
        shell.call(self.make_check, self.meson_dir)


class BuildType (object):

    CUSTOM = CustomBuild
    MAKEFILE = MakefilesBase
    AUTOTOOLS = Autotools
    CMAKE = CMake
    MESON = Meson
