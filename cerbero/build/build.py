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
import subprocess
import asyncio
from pathlib import Path

from cerbero.enums import Platform, Architecture, Distro, LibraryType
from cerbero.errors import FatalError
from cerbero.utils import shell, to_unixpath, add_system_libs
from cerbero.utils import messages as m


def get_optimization_from_config(config):
    if config.variants.optimization:
        if config.target_platform in (Platform.ANDROID, Platform.IOS):
            return 's'
        return '2'
    return '0'


def modify_environment(func):
    '''
    Decorator to modify the build environment

    When called recursively, it only modifies the environment once.
    '''
    def call(*args):
        self = args[0]
        try:
            self._modify_env()
            res = func(*args)
            return res
        finally:
            self._restore_env()

    async def async_call(*args):
        self = args[0]
        try:
            self._modify_env()
            res = await func(*args)
            return res
        finally:
            self._restore_env()

    if asyncio.iscoroutinefunction(func):
        ret = async_call
    else:
        ret = call

    ret.__name__ = func.__name__
    return ret


class EnvVarOp:
    '''
    An operation to be done on the values of a particular env var
    '''
    def __init__(self, op, var, vals, sep):
        self.execute = getattr(self, op)
        self.op = op
        self.var = var
        self.vals = vals
        self.sep = sep

    def set(self, env):
        if not self.vals:
            # An empty array means unset the env var
            if self.var in env:
                del env[self.var]
        else:
            env[self.var] = self.sep.join(self.vals)

    def append(self, env):
        if self.var not in env:
            env[self.var] = self.sep.join(self.vals)
        else:
            env[self.var] += self.sep + self.sep.join(self.vals)

    def prepend(self, env):
        if self.var not in env:
            env[self.var] = self.sep.join(self.vals)
        else:
            old = env[self.var]
            env[self.var] = self.sep.join(self.vals) + self.sep + old

    def remove(self, env):
        if self.var not in env:
            return
        # Split values taking in account spaces and quotes if the
        # separator is ' '
        if self.sep == ' ':
            old = shlex.split(env[self.var])
        else:
            old = env[self.var].split(self.sep)
        new = [x for x in old if x not in self.vals]
        if self.sep == ' ':
            env[self.var] = self.sep.join([shlex.quote(sub) for sub in new])
        else:
            env[self.var] = self.sep.join(new)

    def __repr__(self):
        vals = "None"
        if self.sep:
            vals = self.sep.join(self.vals)
        return "<EnvVarOp " + self.op + " " + self.var + " with " + vals + ">"


class ModifyEnvBase:
    '''
    Base class for build systems and recipes that require extra env variables
    '''

    use_system_libs = False

    def __init__(self):
        # An array of #EnvVarOp operations that will be performed sequentially
        # on the env when @modify_environment is called.
        self._new_env = []
        # Set of env vars that will be modified
        self._env_vars = set()
        # Old environment to restore
        self._old_env = {}

        class ModifyEnvFuncWrapper(object):
            def __init__(this, target, method):
                this.target = target
                this.method = method

            def __call__(this, var, *vals, sep=' ', when='later'):
                if vals == (None,):
                    vals = None
                op = EnvVarOp(this.method, var, vals, sep)
                if when == 'later':
                    this.target.check_reentrancy()
                    this.target._env_vars.add(var)
                    this.target._new_env.append(op)
                elif when == 'now-with-restore':
                    this.target._save_env_var(var)
                    op.execute(this.target.env)
                elif when == 'now':
                    op.execute(this.target.env)
                else:
                    raise RuntimeError('Unknown when value: ' + when)

            def __repr__(this):
                return "<ModifyEnvFuncWrapper " + this.method + " for " + repr(this.target) + "  at " + str(hex(id(this))) + ">"

        for i in ('append', 'prepend', 'set', 'remove'):
            setattr(self, i + '_env', ModifyEnvFuncWrapper(self, i))
        # Setup buildtype args; previously this was done by platform config files
        # Except when using Meson or MSVC
        if not isinstance(self, Meson) and not self.using_msvc():
            self.setup_buildtype_env_ops()

    def setup_buildtype_env_ops(self):
        buildtype_args = '-Wall '
        if self.config.variants.debug:
            buildtype_args += '-g '
        buildtype_args += '-O{} '.format(get_optimization_from_config(self.config))
        for var in ('CFLAGS', 'CXXFLAGS', 'CPPFLAGS', 'OBJCFLAGS'):
            self.append_env(var, buildtype_args)

    def setup_toolchain_env_ops(self):
        if self.config.qt5_pkgconfigdir:
            self.append_env('PKG_CONFIG_LIBDIR', self.config.qt5_pkgconfigdir, sep=os.pathsep)
        if self.config.platform != Platform.WINDOWS:
            return
        if self.using_msvc():
            toolchain_env = self.config.msvc_toolchain_env
        else:
            toolchain_env = self.config.mingw_toolchain_env
        # Set the toolchain environment
        for var, (val, sep) in toolchain_env.items():
            # We prepend PATH and replace the rest
            if var == 'PATH':
                self.prepend_env(var, val, sep=sep)
            else:
                self.set_env(var, val, sep=sep)

    def unset_toolchain_env(self):
        # These toolchain env vars set by us are for GCC, so unset them if
        # we're building with MSVC (or cross-compiling with Meson)
        for var in ('CC', 'CXX', 'OBJC', 'OBJCXX', 'AR', 'WINDRES', 'STRIP',
                    'CFLAGS', 'CXXFLAGS', 'CPPFLAGS', 'OBJCFLAGS', 'LDFLAGS'):
            if var in self.env:
                # Env vars that are edited by the recipe will be restored by
                # @modify_environment when we return from the build step but
                # other env vars won't be, so add those.
                self.set_env (var, None, when='now-with-restore')

            if self.using_msvc():
                # Restore msvc toolchain env which should be preserved
                for key, (val, sep) in self.config.msvc_toolchain_env.items():
                    if var == key:
                        self.set_env(var, val, sep=sep, when='now')
                        break

        # Re-add *FLAGS that weren't set by the toolchain config, but instead
        # were set in the recipe or other places via @modify_environment
        if self.using_msvc():
            for var in ('CFLAGS', 'CXXFLAGS', 'CPPFLAGS', 'OBJCFLAGS',
                        'LDFLAGS', 'OBJLDFLAGS'):
                for each in self._new_env:
                    if var == each.var:
                        each.execute(self.env)

    def check_reentrancy(self):
        if self._old_env:
            raise RuntimeError('Do not modify the env inside @modify_environment, it will have no effect')

    def _save_env_var(self, var):
        # Will only store the first 'save'.
        if var not in self._old_env:
            if var in self.env:
                self._old_env[var] = self.env[var]
            else:
                self._old_env[var] = None

    def _modify_env(self):
        '''
        Modifies the build environment by inserting env vars from new_env
        '''
        # Don't modify env again if already did it once for this function call
        if self._old_env:
            return
        # Store old env
        for var in self._env_vars:
            self._save_env_var (var)
        # Modify env
        for env_op in self._new_env:
            env_op.execute(self.env)

    def _restore_env(self):
        ''' Restores the old environment '''
        for var, val in self._old_env.items():
            if val is None:
                if var in self.env:
                    del self.env[var]
            else:
                self.env[var] = val
        self._old_env.clear()

    def maybe_add_system_libs(self, step=''):
        '''
        Add /usr/lib/pkgconfig to PKG_CONFIG_PATH so the system's .pc file
        can be found.
        '''
        # Note: this is expected to be called with the environment already
        # modified using @{async_,}modify_environment

        # don't add system libs unless explicitly asked for
        if not self.use_system_libs or not self.config.allow_system_libs:
            return;

        # this only works because add_system_libs() does very little
        # this is a possible source of env conflicts
        new_env = {}
        add_system_libs(self.config, new_env, self.env)

        if step != 'configure':
            # gobject-introspection gets the paths to internal libraries all
            # wrong if we add system libraries during compile.  We should only
            # need PKG_CONFIG_PATH during configure so just unset it everywhere
            # else we will get linker errors compiling introspection binaries
            if 'PKG_CONFIG_PATH' in new_env:
                del new_env['PKG_CONFIG_PATH']
        for var, val in new_env.items():
            self.set_env(var, val, when='now-with-restore')


class Build(object):
    '''
    Base class for build handlers

    @ivar recipe: the parent recipe
    @type recipe: L{cerbero.recipe.Recipe}
    @ivar config: cerbero's configuration
    @type config: L{cerbero.config.Config}
    '''

    library_type = LibraryType.BOTH
    # Whether this recipe's build system can be built with MSVC
    can_msvc = False

    def __init__(self):
        self._properties_keys = []

    @modify_environment
    def get_env(self, var, default=None):
        if var in self.env:
            return self.env[var]
        return default

    def using_msvc(self):
        if not self.can_msvc:
            return False
        if not self.config.variants.visualstudio:
            return False
        return True

    async def configure(self):
        '''
        Configures the module
        '''
        raise NotImplemented("'configure' must be implemented by subclasses")

    async def compile(self):
        '''
        Compiles the module
        '''
        raise NotImplemented("'make' must be implemented by subclasses")

    async def install(self):
        '''
        Installs the module
        '''
        raise NotImplemented("'install' must be implemented by subclasses")

    def check(self):
        '''
        Runs any checks on the module
        '''
        pass


class CustomBuild(Build, ModifyEnvBase):

    def __init__(self):
        Build.__init__(self)
        ModifyEnvBase.__init__(self)

    async def configure(self):
        pass

    async def compile(self):
        pass

    async def install(self):
        pass


class MakefilesBase (Build, ModifyEnvBase):
    '''
    Base class for makefiles build systems like autotools and cmake
    '''

    config_sh = ''
    configure_tpl = ''
    configure_options = ''
    make = None
    make_install = None
    make_check = None
    make_clean = None
    allow_parallel_build = True
    srcdir = '.'
    requires_non_src_build = False
    # recipes often use shell constructs
    config_sh_needs_shell = True

    def __init__(self):
        Build.__init__(self)
        ModifyEnvBase.__init__(self)

        self.setup_toolchain_env_ops()

        self.config_src_dir = os.path.abspath(os.path.join(self.build_dir,
                                                           self.srcdir))
        if self.requires_non_src_build:
            self.make_dir = os.path.join (self.config_src_dir, "cerbero-build-dir")
        else:
            self.make_dir = self.config_src_dir

        self.make = self.make or ['make', 'V=1']
        self.make_install = self.make_install or ['make', 'install']
        self.make_clean = self.make_clean or ['make', 'clean']

        if self.config.allow_parallel_build and self.allow_parallel_build \
                and self.config.num_of_cpus > 1:
            self.make += ['-j%d' % self.config.num_of_cpus]

        # Make sure user's env doesn't mess up with our build.
        self.set_env('MAKEFLAGS', when='now')
        # Disable site config, which is set on openSUSE
        self.set_env('CONFIG_SITE', when='now')
        # Only add this for non-meson recipes, and only for iPhoneOS
        if self.config.ios_platform == 'iPhoneOS':
            bitcode_cflags = ['-fembed-bitcode']
            # NOTE: Can't pass -bitcode_bundle to Makefile projects because we
            # can't control what options they pass while linking dylibs
            bitcode_ldflags = bitcode_cflags #+ ['-Wl,-bitcode_bundle']
            self.append_env('ASFLAGS', *bitcode_cflags, when='now')
            self.append_env('CFLAGS', *bitcode_cflags, when='now')
            self.append_env('CXXFLAGS', *bitcode_cflags, when='now')
            self.append_env('OBJCFLAGS', *bitcode_cflags, when='now')
            self.append_env('OBJCXXFLAGS', *bitcode_cflags, when='now')
            self.append_env('CCASFLAGS', *bitcode_cflags, when='now')
            # Autotools only adds LDFLAGS when doing compiler checks,
            # so add -fembed-bitcode again
            self.append_env('LDFLAGS', *bitcode_ldflags, when='now')

    async def configure(self):
        '''
        Base configure method

        When called from a method in deriverd class, that method has to be
        decorated with modify_environment decorator.
        '''
        if not os.path.exists(self.make_dir):
            os.makedirs(self.make_dir)
        if self.requires_non_src_build:
            self.config_sh = os.path.join('../', self.config_sh)

        if self.using_msvc():
            self.unset_toolchain_env()

        substs = {
            'config-sh': self.config_sh,
            'prefix': self.config.prefix,
            'libdir': self.config.libdir,
            'host': self.config.host,
            'target': self.config.target,
            'build': self.config.build,
            'options': self.configure_options,
            'build_dir': self.build_dir,
            'make_dir': self.make_dir,
        }

        # Construct a command list when possible
        if not self.config_sh_needs_shell:
            configure_cmd = []
            for arg in self.configure_tpl.split():
                if arg == '%(options)s':
                    options = self.configure_options
                    if isinstance(options, str):
                        options = options.split()
                    configure_cmd += options
                else:
                    configure_cmd.append(arg % substs)
        else:
            configure_cmd = self.configure_tpl % substs

        self.maybe_add_system_libs(step='configure')

        await shell.async_call(configure_cmd, self.make_dir,
                               logfile=self.logfile, env=self.env)

    @modify_environment
    async def compile(self):
        if self.using_msvc():
            self.unset_toolchain_env()
        self.maybe_add_system_libs(step='compile')
        await shell.async_call(self.make, self.make_dir, logfile=self.logfile, env=self.env)

    @modify_environment
    async def install(self):
        self.maybe_add_system_libs(step='install')
        await shell.async_call(self.make_install, self.make_dir, logfile=self.logfile, env=self.env)

    @modify_environment
    def clean(self):
        self.maybe_add_system_libs(step='clean')
        shell.new_call(self.make_clean, self.make_dir, logfile=self.logfile, env=self.env)

    @modify_environment
    def check(self):
        if self.make_check:
            self.maybe_add_system_libs(step='check')
            shell.new_call(self.make_check, self.build_dir, logfile=self.logfile, env=self.env)


class Makefile (MakefilesBase):
    '''
    Build handler for Makefile project
    '''
    @modify_environment
    async def configure(self):
        await MakefilesBase.configure(self)


class Autotools (MakefilesBase):
    '''
    Build handler for autotools project

    @cvar override_libtool: overrides ltmain.sh to generate a libtool
                            script with the one built by cerbero.
    @type override_libtool: boolean
    '''

    autoreconf = False
    autoreconf_sh = 'autoreconf -f -i'
    config_sh = './configure'
    configure_tpl = "%(config-sh)s --prefix %(prefix)s "\
                    "--libdir %(libdir)s"
    add_host_build_target = True
    can_use_configure_cache = True
    supports_cache_variables = True
    disable_introspection = False
    override_libtool = True

    def __init__(self):
        MakefilesBase.__init__(self)
        self.make_check = self.make_check or ['make', 'check']

    @modify_environment
    async def configure(self):
        # Build with PIC for static linking
        self.configure_tpl += ' --with-pic '
        # Only use --disable-maintainer mode for real autotools based projects
        if os.path.exists(os.path.join(self.config_src_dir, 'configure.in')) or\
                os.path.exists(os.path.join(self.config_src_dir, 'configure.ac')):
            self.configure_tpl += " --disable-maintainer-mode "
            self.configure_tpl += " --disable-silent-rules "
            # Never build gtk-doc documentation
            self.configure_tpl += " --disable-gtk-doc "

        if self.config.variants.gi and not self.disable_introspection \
                and self.use_gobject_introspection():
            self.configure_tpl += " --enable-introspection "
        else:
            self.configure_tpl += " --disable-introspection "

        if self.autoreconf:
            await shell.async_call(self.autoreconf_sh, self.config_src_dir,
                                   logfile=self.logfile, env=self.env)

        # Use our own config.guess and config.sub
        config_datadir = os.path.join(self.config._relative_path('data'), 'autotools')
        cfs = {'config.guess': config_datadir, 'config.sub': config_datadir}
        # ensure our libtool modifications are actually picked up by recipes
        if self.name != 'libtool' and self.override_libtool:
            cfs['ltmain.sh'] = os.path.join(self.config.build_tools_prefix, 'share/libtool/build-aux')
        for cf, srcdir in cfs.items():
            find_cmd = 'find {} -type f -name {}'.format(self.config_src_dir, cf)
            files = await shell.async_call_output(find_cmd, logfile=self.logfile, env=self.env)
            files = files.split('\n')
            files.remove('')
            for f in files:
                o = os.path.join(srcdir, cf)
                m.log("CERBERO: copying %s to %s" % (o, f), self.logfile)
                shutil.copy(o, f)

        if self.config.platform == Platform.WINDOWS and \
                self.supports_cache_variables:
            # On windows, environment variables are upperscase, but we still
            # need to pass things like am_cv_python_platform in lowercase for
            # configure and autogen.sh
            for k, v in self.env.items():
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

        if self._new_env:
            use_configure_cache = False

        if use_configure_cache and self.can_use_configure_cache:
            cache = os.path.join(self.config.sources, '.configure.cache')
            self.configure_tpl += ' --cache-file=%s' % cache

        # Add at the very end to allow recipes to override defaults
        self.configure_tpl += "  %(options)s "

        await MakefilesBase.configure(self)


class CMake (MakefilesBase):
    '''
    Build handler for cmake projects
    '''

    config_sh_needs_shell = False
    config_sh = 'cmake'
    configure_tpl = '%(config-sh)s -DCMAKE_INSTALL_PREFIX=%(prefix)s ' \
                    '-H%(build_dir)s ' \
                    '-B%(make_dir)s ' \
                    '-DCMAKE_LIBRARY_OUTPUT_PATH=%(libdir)s ' \
                    '-DCMAKE_INSTALL_LIBDIR=lib ' \
                    '-DCMAKE_INSTALL_BINDIR=bin ' \
                    '-DCMAKE_INSTALL_INCLUDEDIR=include ' \
                    '%(options)s -DCMAKE_BUILD_TYPE=Release '\
                    '-DCMAKE_FIND_ROOT_PATH=$CERBERO_PREFIX '\
                    '-DCMAKE_POSITION_INDEPENDENT_CODE:BOOL=true . '

    def __init__(self):
        MakefilesBase.__init__(self)
        self.make_dir = os.path.join(self.build_dir, '_builddir')

    @modify_environment
    async def configure(self):
        cc = self.env.get('CC', 'gcc')
        cxx = self.env.get('CXX', 'g++')
        cflags = self.env.get('CFLAGS', '')
        cxxflags = self.env.get('CXXFLAGS', '')
        # FIXME: CMake doesn't support passing "ccache $CC"
        if self.config.use_ccache:
            cc = cc.replace('ccache', '').strip()
            cxx = cxx.replace('ccache', '').strip()
        cc = cc.split(' ')[0]
        cxx = cxx.split(' ')[0]

        if self.configure_options:
            self.configure_options = self.configure_options.split()

        if self.config.target_platform == Platform.WINDOWS:
            self.configure_options += ['-DCMAKE_SYSTEM_NAME=Windows']
        elif self.config.target_platform == Platform.ANDROID:
            self.configure_options += ['-DCMAKE_SYSTEM_NAME=Linux']
        if self.config.platform == Platform.WINDOWS:
            self.configure_options += ['-G', 'Unix Makefiles']

        # FIXME: Maybe export the sysroot properly instead of doing regexp magic
        if self.config.target_platform in [Platform.DARWIN, Platform.IOS]:
            r = re.compile(r".*-isysroot ([^ ]+) .*")
            sysroot = r.match(cflags).group(1)
            self.configure_options += ['-DCMAKE_OSX_SYSROOT=' + sysroot]

        self.configure_options += [
            '-DCMAKE_C_COMPILER=' + cc,
            '-DCMAKE_CXX_COMPILER=' + cxx,
            '-DCMAKE_C_FLAGS=' + cflags,
            '-DCMAKE_CXX_FLAGS=' + cxxflags,
            '-DLIB_SUFFIX=' + self.config.lib_suffix,
        ]

        cmake_cache = os.path.join(self.make_dir, 'CMakeCache.txt')
        cmake_files = os.path.join(self.make_dir, 'CMakeFiles')
        if os.path.exists(cmake_cache):
            os.remove(cmake_cache)
        if os.path.exists(cmake_files):
            shutil.rmtree(cmake_files)
        self.make += ['VERBOSE=1']
        await MakefilesBase.configure(self)


MESON_CROSS_FILE_TPL = \
'''
[host_machine]
system = '{system}'
cpu_family = '{cpu_family}'
cpu = '{cpu}'
endian = '{endian}'

[properties]
{extra_properties}

[binaries]
c = {CC}
cpp = {CXX}
ar = {AR}
pkgconfig = 'pkg-config'
{extra_binaries}
'''

MESON_NATIVE_FILE_TPL = \
'''
[binaries]
{extra_binaries}
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
    meson_options = None
    meson_cross_properties = None
    meson_backend = 'ninja'
    # All meson recipes are MSVC-compatible, except if the code itself isn't
    can_msvc = True
    meson_builddir = "_builddir"

    def __init__(self):
        self.meson_options = self.meson_options or {}

        Build.__init__(self)
        ModifyEnvBase.__init__(self)

        self.setup_toolchain_env_ops()

        cross_props = copy.deepcopy(self.config.meson_cross_properties)
        cross_props.update(self.config.meson_cross_properties or {})
        self.meson_cross_properties = cross_props

        # Find Meson
        if not self.meson_sh:
            # meson installs `meson.exe` on windows and `meson` on other
            # platforms that read shebangs
            self.meson_sh = os.path.join(self.config.build_tools_prefix, 'bin', 'meson')

        # Find ninja
        if not self.make:
            self.make = ['ninja', '-v', '-d', 'keeprsp']
        if not self.make_install:
            self.make_install = self.make + ['install']
        if not self.make_check:
            self.make_check = self.make + ['test']
        if not self.make_clean:
            self.make_clean = self.make + ['clean']

    @staticmethod
    def _get_option_value(opt_type, value):
        if opt_type == 'feature':
            return 'enabled' if value else 'disabled'
        if opt_type == 'boolean':
            return 'true' if value else 'false'
        raise AssertionError('Invalid option type {!r}'.format(opt_type))

    def _set_option(self, opt_names, variant_name):
        '''
        Parse the meson_options.txt file, figure out whether any of the provided option names exist,
        figure out the type, and enable/disable it as per the cerbero configuration.
        '''
        # Don't overwrite if it's already set
        if opt_names.intersection(self.meson_options):
            return
        # Error out on invalid usage
        if not os.path.isdir(self.build_dir):
            raise FatalError('Build directory doesn\'t exist yet?')
        # Check if the option exists, and if so, what the type is
        meson_options = os.path.join(self.build_dir, 'meson_options.txt')
        if not os.path.isfile(meson_options):
            return
        opt_name = None
        opt_type = None
        with open(meson_options, 'r') as f:
            options = f.read()
            # iterate over all option()s individually
            option_regex = "option\s*\(\s*(?:'(?P<name>[^']+)')\s*,\s*(?P<entry>(?P<identifier>[a-zA-Z0-9]+)\s*:\s*(?:(?P<string>'[^']+')|[^'\),\s]+)\s*,?\s*)+\)"
            for match in re.finditer(option_regex, options, re.MULTILINE):
                option = match.group(0)
                # find the option(), if it exists
                opt_name = match.group('name')
                if opt_name in opt_names:
                    # get the type of the option
                    type_regex = "type\s*:\s*'(?P<type>[^']+)'"
                    ty = re.search (type_regex, option, re.MULTILINE)
                    if ty and ty.group('type') in ('feature', 'boolean'):
                        opt_type = ty.group('type')
                        break
                    else:
                        raise FatalError('Unable to detect type of option {!r}'.format(opt_name))
        if opt_name and opt_type:
            value = getattr(self.config.variants, variant_name) if variant_name else False
            self.meson_options[opt_name] = self._get_option_value(opt_type, value)

    def _get_cpu_family(self):
        if Architecture.is_arm(self.config.target_arch):
            if Architecture.is_arm32(self.config.target_arch):
                return 'arm'
            else:
                return 'aarch64'
        return self.config.target_arch

    def _get_moc_path(self, qmake_path):
        qmake = Path(qmake_path)
        moc_name = qmake.name.replace('qmake', 'moc')
        return str(qmake.parent / moc_name)

    def _write_meson_cross_file(self):
        # Take cross toolchain from _old_env because we removed them from the
        # env so meson doesn't detect them as the native toolchain.
        # Same for *FLAGS below.
        if self.using_msvc():
            cc = ['cl']
            cxx = ['cl']
            ar = ['lib']
        else:
            cc = self.env['CC'].split()
            cxx = self.env['CXX'].split()
            ar = self.env['AR'].split()
        strip = self.env.get('STRIP', '').split()
        windres = self.env.get('WINDRES', '').split()

        # We do not use cmake dependency files, speed up the build by disabling it
        cross_binaries = {'cmake': ['false']}
        if 'STRIP' in self.env:
            cross_binaries['strip'] = self.env['STRIP'].split()
        if 'WINDRES' in self.env:
            cross_binaries['windres'] = self.env['WINDRES'].split()
        if 'OBJC' in self.env:
            cross_binaries['objc'] = self.env['OBJC'].split()
        if 'OBJCXX' in self.env:
            cross_binaries['objcpp'] = self.env['OBJCXX'].split()
        if self.config.qt5_qmake_path:
            cross_binaries['qmake'] = [self.config.qt5_qmake_path]
            cross_binaries['moc'] = [self._get_moc_path(self.config.qt5_qmake_path)]

        # *FLAGS are only passed to the native compiler, so while
        # cross-compiling we need to pass these through the cross file.
        c_args = shlex.split(self.env.get('CFLAGS', ''))
        cpp_args = shlex.split(self.env.get('CXXFLAGS', ''))
        objc_args = shlex.split(self.env.get('OBJCFLAGS', ''))
        objcpp_args = shlex.split(self.env.get('OBJCXXFLAGS', ''))
        # Link args
        c_link_args = shlex.split(self.env.get('LDFLAGS', ''))
        cpp_link_args = c_link_args
        if 'OBJLDFLAGS' in self.env:
            objc_link_args = shlex.split(self.env['OBJLDFLAGS'])
        else:
            objc_link_args = c_link_args
        objcpp_link_args = objc_link_args

        # Operate on a copy of the recipe properties to avoid accumulating args
        # from all archs when doing universal builds
        cross_properties = copy.deepcopy(self.meson_cross_properties)
        for args in ('c_args', 'cpp_args', 'objc_args', 'objcpp_args',
                     'c_link_args', 'cpp_link_args', 'objc_link_args',
                     'objcpp_link_args'):
            if args in cross_properties:
                cross_properties[args] += locals()[args]
            else:
                cross_properties[args] = locals()[args]

        extra_properties = ''
        for k, v in cross_properties.items():
            extra_properties += '{} = {}\n'.format(k, str(v))

        extra_binaries = ''
        for k, v in cross_binaries.items():
            extra_binaries += '{} = {}\n'.format(k, str(v))

        # Create a cross-info file that tells Meson and GCC how to cross-compile
        # this project
        cross_file = os.path.join(self.meson_dir, 'meson-cross-file.txt')
        contents = MESON_CROSS_FILE_TPL.format(
                system=self.config.target_platform,
                cpu=self.config.target_arch,
                cpu_family=self._get_cpu_family(),
                # Assume all ARM sub-archs are in little endian mode
                endian='little',
                CC=cc,
                CXX=cxx,
                AR=ar,
                extra_binaries=extra_binaries,
                extra_properties=extra_properties)
        with open(cross_file, 'w') as f:
            f.write(contents)

        return cross_file

    def _write_meson_native_file(self):
        # We do not use cmake dependency files, speed up the build by disabling it
        native_binaries = {'cmake': ['false']}
        if self.config.qt5_qmake_path:
            native_binaries['qmake'] = [self.config.qt5_qmake_path]
            native_binaries['moc'] = [self._get_moc_path(self.config.qt5_qmake_path)]

        extra_binaries = ''
        for k, v in native_binaries.items():
            extra_binaries += '{} = {}\n'.format(k, str(v))

        native_file = os.path.join(self.meson_dir, 'meson-native-file.txt')
        contents = MESON_NATIVE_FILE_TPL.format(extra_binaries=extra_binaries)
        with open(native_file, 'w') as f:
            f.write(contents)

        return native_file

    @modify_environment
    async def configure(self):
        # self.build_dir is different on each call to configure() when doing universal builds
        self.meson_dir = os.path.join(self.build_dir, self.meson_builddir)
        if os.path.exists(self.meson_dir):
            # Only remove if it's not empty
            if os.listdir(self.meson_dir):
                shutil.rmtree(self.meson_dir)
                os.makedirs(self.meson_dir)
        else:
            os.makedirs(self.meson_dir)

        # Explicitly enable/disable introspection, same as Autotools
        self._set_option({'introspection', 'gir'}, 'gi')
        # Control python support using the variant
        self._set_option({'python'}, 'python')
        # Always disable gtk-doc, same as Autotools
        self._set_option({'gtk_doc'}, None)
        # Automatically disable examples
        self._set_option({'examples'}, None)

        # NOTE: self.tagged_for_release is set in recipes/custom.py
        is_gstreamer_recipe = hasattr(self, 'tagged_for_release')
        # Enable -Werror for gstreamer recipes and when running under CI
        if is_gstreamer_recipe and self.config.variants.werror:
            # Let recipes override the value
            if 'werror' not in self.meson_options:
                self.meson_options['werror'] = 'true'

        debug = 'true' if self.config.variants.debug else 'false'
        opt = get_optimization_from_config(self.config)

        if self.library_type == LibraryType.NONE:
            raise RuntimeException("meson recipes cannot be LibraryType.NONE")

        meson_cmd = [self.meson_sh, '--prefix=' + self.config.prefix,
            '--libdir=lib' + self.config.lib_suffix, '-Ddebug=' + debug,
            '--default-library=' + self.library_type, '-Doptimization=' + opt,
            '--backend=' + self.meson_backend, '--wrap-mode=nodownload']

        if self.using_msvc():
            meson_cmd.append('-Db_vscrt=' + self.config.variants.vscrt)

        # Don't enable bitcode by passing flags manually, use the option
        if self.config.ios_platform == 'iPhoneOS':
            self.meson_options.update({'b_bitcode': 'true'})
        if self.config.cross_compiling():
            meson_cmd += ['--cross-file', self._write_meson_cross_file()]
        meson_cmd += ['--native-file', self._write_meson_native_file()]

        if self.config.cross_compiling() or self.using_msvc():
            # We export the cross toolchain with env vars, but Meson picks the
            # native toolchain from these, so unset them.
            # FIXME: https://bugzilla.gnome.org/show_bug.cgi?id=791670
            # NOTE: This means we require a native compiler on the build
            # machine when cross-compiling, which in practice is not a problem
            #
            # Also, on Windows these toolchain env vars set by us are for GCC,
            # so unset them if we're building with MSVC
            self.unset_toolchain_env()

        if 'default_library' in self.meson_options:
            raise RuntimeError('Do not set `default_library` in self.meson_options, use self.library_type instead')

        for (key, value) in self.meson_options.items():
            meson_cmd += ['-D%s=%s' % (key, str(value))]

        self.maybe_add_system_libs(step='configure')
        await shell.async_call(meson_cmd, self.meson_dir, logfile=self.logfile, env=self.env)

    @modify_environment
    async def compile(self):
        self.maybe_add_system_libs(step='compile')
        await shell.async_call(self.make, self.meson_dir, logfile=self.logfile, env=self.env)

    @modify_environment
    async def install(self):
        self.maybe_add_system_libs(step='install')
        await shell.async_call(self.make_install, self.meson_dir, logfile=self.logfile, env=self.env)

    @modify_environment
    def clean(self):
        self.maybe_add_system_libs(step='clean')
        shell.new_call(self.make_clean, self.meson_dir, logfile=self.logfile, env=self.env)

    @modify_environment
    def check(self):
        self.maybe_add_system_libs(step='check')
        shell.new_call(self.make_check, self.meson_dir, logfile=self.logfile, env=self.env)


class BuildType (object):

    CUSTOM = CustomBuild
    MAKEFILE = Makefile
    AUTOTOOLS = Autotools
    CMAKE = CMake
    MESON = Meson
