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
import glob
import shutil
import inspect
from functools import partial
import shlex
from pathlib import Path
from typing import Optional, List

from cerbero.config import Platform, LibraryType
from cerbero.enums import Distro, Symbolication
from cerbero.tools import dsymutil
from cerbero.utils import shell
from cerbero.utils import messages as m
from cerbero.errors import FatalError
from cerbero.build.build import BuildType


def find_shlib_regex(config, libname, prefix, libdir, ext, regex):
    # Use globbing to find all files that look like they might match
    # this library to narrow down our exact search
    fpath = os.path.join(libdir, '*{0}*{1}*'.format(libname, ext))
    found = glob.glob(Path(prefix, fpath).as_posix())
    # Find which of those actually match via an exact regex
    # Ideally Python should provide a function for regex file 'globbing'
    matches = []
    for each in found:
        fname = os.path.basename(each)
        if re.match(regex.format(re.escape(libname)), fname):
            matches.append(Path(libdir, fname).as_posix())
    return matches


def get_implib_dllname(config, path):
    if config.msvc_env_for_toolchain and path.endswith('.lib'):
        lib_exe = shutil.which('lib', path=config.msvc_env_for_toolchain['PATH'].get())
        if not lib_exe:
            raise FatalError('lib.exe not found, check cerbero configuration')
        try:
            ret = shell.check_output([lib_exe, '-list', path], env=config.env)
        except FatalError:
            return None
        # The last non-empty line should contain the dllname
        return ret.split('\n')[-2]
    dlltool = config.env.get('DLLTOOL', None)
    if not dlltool:
        raise FatalError('dlltool not found, check cerbero configuration')
    try:
        return shell.check_output(shlex.split(dlltool) + ['-I', path], env=config.env)
    except FatalError:
        return None


def find_dll_implib(config, libname, prefix, libdir, ext, regex):
    implibdir = 'lib'
    implibs = ['lib{}.dll.a'.format(libname), libname + '.lib', 'lib{}.lib'.format(libname)]
    implib_notfound = []
    for implib in implibs:
        path = Path(prefix, implibdir, implib).as_posix()
        if not os.path.exists(path):
            implib_notfound.append(implib)
            continue
        dllname = get_implib_dllname(config, path)
        if not dllname:
            continue
        dllname = dllname.strip()
        if not dllname:
            continue
        if dllname.endswith('.obj'):
            # Ban .lib that are static libraries e.g. unfixed cURL recipe
            continue
        return [Path(libdir, dllname).as_posix()]
    # If import libraries aren't found, look for a DLL by exactly the specified
    # name. This is to cover cases like libgcc_s_sjlj-1.dll which don't have an
    # import library since they're only used at runtime.
    dllname = 'lib{}.dll'.format(libname)
    path = Path(prefix, libdir, dllname).as_posix()
    if os.path.exists(path):
        return [Path(libdir, dllname).as_posix()]
    else:
        # MinGW convention -- libfoo-1.0-0.dll, strip prefix and suffix
        # and glob for soversion
        libname = libname.removeprefix('lib').removesuffix('.dll')
        glob = set(Path(prefix, libdir).glob(f'lib{libname}-*.dll'))
        if len(glob) == 1:
            return list(f.as_posix() for f in glob)
        # zlib convention e.g. when buildtools
        glob = set(Path(prefix, libdir).glob(f'{libname}-*.dll'))
        if len(glob) == 1:
            return list(f.as_posix() for f in glob)
    if len(implib_notfound) == len(implibs):
        m.warning('No import libraries found for {!r}'.format(libname))
    else:
        implibs = ', '.join(set(implibs) - set(implib_notfound))
        m.warning('No dllname found from implibs: {}'.format(implibs))
    # This will trigger an error in _list_libraries()
    return []


def find_pdb_implib(config, libname, prefix, debugext):
    dlls = find_dll_implib(config, libname, prefix, 'bin', None, None)
    pdbs = []
    for dll in dlls:
        pdb = [
            dll + debugext,  # .so.debuginfo
            dll[:-4] + debugext,  # .debuginfo, .pdb
        ]
        for f in pdb:
            if Path(prefix, f).exists():
                pdbs.append(f)
    return pdbs


class FilesProvider(object):
    """
    List files by categories using class attributes named files_$category and
    platform_files_$category
    """

    LIBS_CAT = 'libs'
    BINS_CAT = 'bins'
    PY_CAT = 'python'
    # devel is implemented as "all files that aren't in any other category"
    DEVEL_CAT = 'devel'
    LANG_CAT = 'lang'
    TYPELIB_CAT = 'typelibs'
    # DLLs can be named anything, there may not be any correlation between that
    # and the import library (which is actually used while linking), so don't
    # try to use a regex. Instead, get the dll name from the import library.
    _DLL_REGEX = None
    # UNIX shared libraries can have between 0 and 3 version components:
    # major, minor, micro. We don't use {m,n} here because we want to capture
    # all the matches.
    _ANDROID_SO_REGEX = r'^lib{}\.so(\.[0-9]+)?(\.[0-9]+)?(\.[0-9]+)?$'
    # Like _ANDROID_SO_REGEX but only libs with version number.
    _LINUX_SO_REGEX = r'^lib{}\.so(\.[0-9]+)(\.[0-9]+)?(\.[0-9]+)?$'
    _DYLIB_REGEX = r'^lib{}(\.[0-9]+)?(\.[0-9]+)?(\.[0-9]+)?\.dylib$'

    # Extension Glob Legend:
    # bext = binary extension
    # sext = shared library matching regex
    # srext = shared library extension (no regex)
    # sdir = shared library directory
    # mext = module (plugin) extension
    # smext = static module (plugin) extension
    # pext = python module extension (.pyd on Windows)
    # libdir = relative libdir path (lib, lib64, lib/i386-linux-gnu)
    EXTENSIONS = {
        Platform.WINDOWS: {
            'bext': '.exe',
            'sregex': _DLL_REGEX,
            'mext': '.dll',
            'smext': '.a',
            'pext': '.pyd',
            'srext': '.dll',
            'debugext': None,  # see later
        },
        Platform.LINUX: {
            'bext': '',
            'sregex': _LINUX_SO_REGEX,
            'mext': '.so',
            'smext': '.a',
            'pext': '.so',
            'srext': '.so',
            'debugext': '.debuginfo',
        },
        Platform.ANDROID: {
            'bext': '',
            'sregex': _ANDROID_SO_REGEX,
            'mext': '.so',
            'smext': '.a',
            'pext': '.so',
            'srext': '.so',
            'debugext': None,  # Disallow stripping
        },
        Platform.DARWIN: {
            'bext': '',
            'sregex': _DYLIB_REGEX,
            'mext': '.so',
            'smext': '.a',
            'pext': '.so',
            'srext': '.dylib',
            'debugext': '.dSYM',
        },
        Platform.IOS: {
            'bext': '',
            'sregex': _DYLIB_REGEX,
            'mext': '.so',
            'smext': '.a',
            'pext': '.so',
            'srext': '.dylib',
            'debugext': '.dSYM',
        },
    }

    # Match static gstreamer plugins, GIO modules, etc.
    _FILES_STATIC_PLUGIN_REGEX = re.compile(r'lib/.+/lib(gst|)([^/.]+)\.a')

    def __init__(self, config):
        self.config = config
        self.platform = config.target_platform
        self.extensions = self.EXTENSIONS[self.platform].copy()
        self.extensions['pydir'] = str(config.get_python_prefix())
        self.extensions['pext'] = config.get_python_ext_suffix()
        self.extensions['pyplatdir'] = config.py_plat_prefix
        self.extensions['libdir'] = self.config.rel_libdir
        if self.platform == Platform.WINDOWS:
            self.extensions['sdir'] = 'bin'
        else:
            self.extensions['sdir'] = self.extensions['libdir']
        if self._dylib_plugins():
            self.extensions['mext'] = '.dylib'
        self._findlibfunc = None
        if self.extensions['sregex']:
            self._findlibfunc = find_shlib_regex
        elif self.config.target_platform == Platform.WINDOWS:
            self._findlibfunc = find_dll_implib
        else:
            raise AssertionError
        if self.using_msvc():
            self.extensions['debugext'] = '.pdb'
        elif self.platform == Platform.WINDOWS:
            self.extensions['debugext'] = '.debuginfo'
        self.py_prefixes = config.py_prefixes
        self.add_license_files()
        self.update_categories()
        self._listfuncs = {
            self.LIBS_CAT: self._list_libraries,
            self.BINS_CAT: self._list_binaries,
            self.PY_CAT: self._list_pyfiles,
            self.LANG_CAT: self._list_langfiles,
            self.TYPELIB_CAT: self._list_typelibfiles,
            'default': self._list_files,
        }

    def _search_file(self, file):
        """
        Search for arbitrary files doing the extension replacements, globbing, and listing
        directories
        """
        # fill directories
        if os.path.isdir(Path(self.config.prefix, file).as_posix()):
            found = self._ls_dir(Path(self.config.prefix, file).as_posix())
        else:
            found = shell.ls_files([file], self.config.prefix)
        return found

    def _search_library(self, file):
        """
        Search libraries in the prefix. Unfortunately the filename might vary
        depending on the platform and we need to match the library name and
        it's extension. There is a corner case on windows where the DLL might
        have any name, so we search for the .lib or .dll.a import library
        and get the DLL name from that.
        """
        libdir = self.extensions['sdir']
        libext = self.extensions['srext']
        libregex = self.extensions['sregex']
        f = os.path.basename(file)
        # Extract the libname again. This might be redundant, but it is done
        # like this to avoid changing all the library search implementations
        pattern = r'\*?(?P<libname>[^\*]*)\*?{}\*?'.format(libext)
        m = re.match(pattern, f)
        f = m.group('libname')
        libsmatch = self._findlibfunc(self.config, f[3:], self.config.prefix, libdir, libext, libregex)
        return libsmatch

    def _search_library_pdb(self, file):
        stem = os.path.basename(file)
        abspath = Path(self.config.prefix, file).resolve()
        if abspath.suffix == self.extensions['debugext'] and abspath.exists() and stem == abspath.name:
            # Straightforward symbol file (plugin, binary)
            # (check stem so that flac.pdb doesn't match FLAC(-8).pdb)
            return [file]
        elif self.config.target_platform == Platform.WINDOWS:
            # try implib
            libname = abspath.stem
            if (
                libname.startswith('lib')
                or libname.endswith(self.extensions['srext'])
                or libname.endswith(self.extensions['mext'])
            ):
                # If looking up PDBs (libfoo.dll.debuginfo)...
                libname = os.path.splitext(libname)[0].removeprefix('lib')
            libs = find_pdb_implib(self.config, libname, self.config.prefix, self.extensions['debugext'])
            if libs:
                return libs
        # Look shared object up, try SOVERSIONing
        # e.g. frei0r-plugins, libgst*, gst-plugins-rs
        libs = [
            abspath.with_suffix('').with_suffix(self.extensions['srext']),
            abspath.with_suffix('').with_suffix(self.extensions['mext']),
        ]
        for lib in filter(lambda f: f.exists(), libs):
            dSYM = abspath.with_stem(lib.resolve().name)
            # Now test it against the resolved SOVERSION'd dylib
            if dSYM.exists():
                return [dSYM.relative_to(self.config.prefix).as_posix()]

        return []

    def _search_binary_pdb(self, file):
        """
        Looks up pdbs for binaries matching either themselves
        or the Rust convention cargo-capi.exe -> cargo_capi.pdb
        """
        files_list = self._search_file(file)
        if files_list:
            return files_list
        return self._search_file(file.replace('-', '_'))

    def _validate_existing(self, files, only_existing=True, with_symbols=True):
        if not only_existing:
            nonvalidated = []
            for each in files:
                nonvalidated.append(each)
            return nonvalidated

        # Validate all the files with the ones in the prefix
        vfs = []
        for f, searchfunc in files.items():
            if not searchfunc:
                searchfunc = self._search_file
            validated = searchfunc(f)
            if validated:
                vfs.extend(validated)
            elif not with_symbols:
                if self.extensions['debugext']:
                    if str(f).endswith(self.extensions['debugext']):
                        continue
            else:
                m.warning('Missing on-disk files for {} with search function {}'.format(f, searchfunc.__name__))
        return vfs

    def _dylib_plugins(self):
        if self.btype not in (BuildType.MESON, BuildType.CARGO_C):
            return False
        if not Platform.is_apple(self.platform):
            return False
        # gstreamer plugins on macOS and iOS use the .dylib extension when
        # built with Meson but modules that use GModule do not
        if not self.name.startswith('gst') and self.name != 'libnice':
            return False
        return True

    def have_symbol_files(self):
        if self.config.variants.nodebug:
            return False
        if self.library_type in (LibraryType.STATIC, LibraryType.NONE):
            return False
        if self.config.target_platform == Platform.ANDROID:
            return False  # Android Studio handles it
        return True

    def add_license_files(self):
        """
        Ensure that all license files are packaged
        """
        if not hasattr(self, 'files_devel'):
            self.files_devel = []
        if self.licenses or getattr(self, 'licenses_bins', None):
            self.files_devel.append('share/licenses/{}'.format(self.name))

    def _list_devel_binaries(self):
        """
        All binaries have a corresponding .pdb/dwp/dSYM file
        that must be included in the devel package. This files list
        is identical to `self.files_bins`, but it is no longer identical
        in lifetime because symbols are generated for macOS after
        relocation (non universal) or after merging (universal).
        """
        pdbs = []
        if hasattr(self, 'files_bins') and self.extensions['debugext']:
            files_bins = self.files_list_by_category(self.BINS_CAT)
            # dsymutil expects files to exist
            files_bins = dsymutil.symbolicable_files(files_bins, self.config.prefix, self.config.target_platform)
            for f in files_bins:
                f_rel = os.path.relpath(f, self.config.prefix)
                if self.config.target_platform == Platform.WINDOWS:
                    # .exe, .dll -> .pdb, .debuginfo
                    f_rel, _ = os.path.splitext(f_rel)
                pdbs.append('{}{}'.format(f_rel, self.extensions['debugext']))
        return {k: self._search_binary_pdb for k in pdbs}

    def _list_misc_binaries(self):
        pdbs = []
        if hasattr(self, 'files_misc') and self.extensions['debugext']:
            files_bins = self.files_list_by_category('misc')
            files_bins = dsymutil.symbolicable_files(
                files_bins,
                self.config.prefix,
                self.config.target_platform,
            )
            for f in files_bins:
                f_rel = os.path.relpath(f, self.config.prefix)
                if self.config.target_platform == Platform.WINDOWS:
                    # .exe, .dll -> .pdb, .debuginfo
                    f_rel, _ = os.path.splitext(f_rel)
                pdbs.append('{}{}'.format(f_rel, self.extensions['debugext']))
        return {k: self._search_binary_pdb for k in pdbs}

    def debug_files_list(self, only_existing=True):
        if not self.have_symbol_files():
            return []
        libs, devfiles = self._list_devel_libraries()
        files = self.devel_files_list(False) + list(libs.keys())
        devfiles.update(self._list_devel_binaries())
        devfiles.update(self._list_misc_binaries())
        devfiles.update(self._list_plugins_dsyms(files))
        devfiles = self._validate_existing(devfiles, only_existing, True)
        return sorted(list(set(devfiles)))

    def _debug_files_list_by_category(self, category):
        if category.endswith(self.DEVEL_CAT):
            return {}
        elif category == self.BINS_CAT:
            return self._list_devel_binaries()
        elif category == 'files_misc':
            return self._list_misc_binaries()
        elif category.startswith(self.LIBS_CAT):
            _, pdbs = self._list_devel_libraries_by_categories([category])
            return pdbs
        else:
            # FIXME: plugins are derived from devel_files_list
            pdbs = {}
            files = {}
            for k, v in self._list_files_by_category(category).items():
                if k.endswith(self.extensions['debugext']):
                    pdbs[k] = v
                else:
                    files[k] = v
            files = self._validate_existing(files)
            files_bins = dsymutil.symbolicable_files(files, self.config.prefix, self.config.target_platform)
            files_bins = [os.path.relpath(f, self.config.prefix) for f in files_bins]
            pdbs.update(self._list_plugins_dsyms(files_bins))
            return pdbs

    def debug_files_list_by_categories(self, categories, only_existing=True):
        if not self.have_symbol_files():
            return []
        if 'debugext' not in self.extensions:
            return []
        files = {}
        for cat in categories:
            cat_files = self._debug_files_list_by_category(cat)
            files.update(cat_files)
        devfiles = self._validate_existing(files, only_existing, True)
        return sorted(list(set(devfiles)))

    def devel_files_list(self, only_existing=True):
        """
        Return the list of development files, which consists in the files and
        directories listed in the 'devel' category and the link libraries .a,
        .la and .so from the 'libs' category
        """
        devfiles = {}
        devfiles.update(self._list_files_by_category(self.DEVEL_CAT))
        devfiles.update(self._list_girfiles())
        devfiles.update(self._list_devel_libraries()[0])
        devfiles = self._validate_existing(devfiles, only_existing, False)
        return sorted(list(set(devfiles)))

    def dist_files_list(self, only_existing=True):
        """
        Return the list of files that should be included in a distribution
        tarball, which include all files except the development files
        """

        distfiles = {}
        for x in self.categories:
            if x.endswith(self.DEVEL_CAT):
                continue
            distfiles.update(self._list_files_by_category(x))
        distfiles = self._validate_existing(distfiles, only_existing)
        return sorted(list(set(distfiles)))

    def files_list(self, only_existing=True):
        """
        Return the complete list of files
        """
        files = self.dist_files_list(only_existing)
        files.extend(self.devel_files_list(only_existing))
        return sorted(list(set(files)))

    def files_list_by_categories(self, categories, only_existing=True):
        """
        Return the list of files in a list categories
        """
        files = {}
        for cat in categories:
            cat_files = self._list_files_by_category(cat)
            files.update(cat_files)
        files = self._validate_existing(files, only_existing, False)
        return sorted(list(set(files)))

    def files_list_by_category(self, category, only_existing=True):
        """
        Return the list of files in a given category
        """
        return self.files_list_by_categories([category], only_existing)

    def libraries(self):
        """
        Return a dict of the library names and library paths
        """
        libraries = {}
        files = self._list_files_by_category(self.LIBS_CAT)
        for f, searchfunc in files.items():
            if not searchfunc:
                searchfunc = self._search_file
            start = len(self.extensions['sdir']) + 1 + 3
            end = len(self.extensions['srext'])
            if self.extensions['sregex']:
                start += 1
                end += 2
            libname = f[start:-end]
            libraries[libname] = searchfunc(f)
        return libraries

    def symbolicable_files(self):
        """
        Prepare the list of automatically and manually symbolicable files
        """
        # only_existing=True is necessary to resolve SOVERSION'd
        # or prefixed libraries
        files_list = self.dist_files_list(only_existing=self.config.target_platform == Platform.WINDOWS)
        patterns = getattr(self, 'symbolication_patterns', {})

        # If files are automatically convertible (GNU)
        if self.config.is_automatically_symbolicable():
            return (files_list, [])
        # If patterns are empty *all* files must be manually symbolicated
        elif getattr(self, 'symbolicate_manually', False) and not any(patterns.values()):
            return ([], files_list)

        auto_sym = set()
        manual_sym = set()
        skip_patterns = patterns.get(Symbolication.SKIP, [])
        manual_patterns = patterns.get(Symbolication.MANUAL, [])
        for f in files_list:
            if any(p in f for p in skip_patterns):
                continue
            elif any(p in f for p in manual_patterns):
                manual_sym.add(f)
            else:
                auto_sym.add(f)
        return (auto_sym, manual_sym)

    def use_gobject_introspection(self):
        return self.TYPELIB_CAT in self._files_categories()

    def update_categories(self):
        self.categories = self._files_categories()

    def _files_categories(self):
        """Get the list of categories available"""
        categories = []
        for name, value in inspect.getmembers(self):
            if not isinstance(value, (dict, list)):
                continue
            if name.startswith('files_'):
                categories.append(name.split('files_')[1])
            if name.startswith('platform_files_'):
                categories.append(name.split('platform_files_')[1])
        return sorted(list(set(categories)))

    def _get_category_files_list(self, category):
        """
        Get the raw list of files in a category, without pattern match nor
        extensions replacement, which should be done in the search function
        """
        files = []
        for attr in dir(self):
            if attr.startswith('files_') and attr.endswith('_' + category):
                files.extend(getattr(self, attr))
            if attr.startswith('platform_files_') and attr.endswith('_' + category):
                files.extend(getattr(self, attr).get(self.platform, []))
        return files

    def _list_files_by_category(self, category):
        search_category = category
        if category.startswith(self.LIBS_CAT + '_'):
            search_category = self.LIBS_CAT
        search = self._listfuncs.get(search_category, self._listfuncs['default'])
        return search(self._get_category_files_list(category))

    @staticmethod
    def _get_msvc_dll(f):
        f = Path(f)
        return str(f.with_name(f.name[3:]))

    @staticmethod
    def _get_plugin_pc(f):
        f = Path(f)
        return str(f.parent / 'pkgconfig' / (f.name[3:-3] + '.pc'))

    def _list_files(self, files):
        """
        List plugin files and arbitrary files in the prefix

        FIXME: Currently plugins are also searched using this, but there should
        be a separate system for those.
        """
        # replace extensions
        files_expanded = []
        for f in files:
            # Don't add shared plugin files when building only static plugins
            if '%(mext)s' in f and self.library_type == LibraryType.STATIC:
                continue
            files_expanded.append(f % self.extensions)
        fs = {}
        for f in files_expanded:
            # Find frei0r plugins wholesale
            if f.endswith('.dll') and self.using_msvc() and '*' not in f:
                fs[self._get_msvc_dll(f)] = None
            # librsvg's pixbufloader
            elif f.endswith('.dll') and not self.using_msvc() and 'gdk-pixbuf-2.0' in f:
                fs[self._get_msvc_dll(f)] = None
            else:
                fs[f] = None
            # For plugins, the .la file is generated using the .pc file, but we
            # don't add the .pc to files_devel. It has the same name, so we can
            # add it using the .la entry.
            if (
                self.platform == Platform.ANDROID
                and f.startswith(self.extensions['libdir'] + '/gstreamer-1.0/')
                and f.endswith('.la')
            ):
                fs[self._get_plugin_pc(f)] = None

        # And suppress .la files
        if self.platform != Platform.ANDROID:
            fs = {k: v for k, v in fs.items() if not k.endswith('.la')}

        return fs

    def _list_plugins_dsyms(self, files):
        """
        Add PDBs/dwp/dSYMs for the given list of plugins
        """
        fs = {}
        skip_files = set(f % self.extensions for f in getattr(self, 'skip_pdb_files', []))
        for f in files:
            if f in skip_files:
                continue
            # Switching here from a regex to manual checks to allow
            # for finding frei0r's symbol files.
            fpath = Path(f)
            fdir = str(fpath.parent)
            m = fpath.stem
            # Skip non plugin files
            if fpath.parts[0] != 'lib':
                continue
            # Skip import libraries etc.
            if len(fpath.suffixes) != 1:
                continue
            # Skip non plugin files
            if self.config.target_distro == Distro.DEBIAN and len(fpath.parts) != 4:
                continue
            elif len(fpath.parts) != 3:
                continue
            # Skip non library files
            if fpath.suffix not in (
                self.extensions['mext'],
                self.extensions['smext'],
                self.extensions['pext'],
                self.extensions['srext'],
            ):
                if not self.extensions['sregex']:
                    continue
                if not re.match(self.extensions['sregex'], fpath.name):
                    continue
            if self.using_msvc():
                # Plugin DLLs are required to be foo.dll when the recipe uses MSVC, and
                # will be in the same directory as the .a static plugin/library
                pdb = '{}/{}{}'.format(fdir, m.removeprefix('lib'), self.extensions['debugext'])
            else:
                # Apple and GNU convention is
                # prefixfoo.soversion.ext.dSYM
                pdb = '{}/lib{}%(mext)s%(debugext)s'.format(fdir, m.removeprefix('lib')) % self.extensions
            fs[pdb] = None
        return fs

    def _list_binaries(self, files):
        """
        List binaries in the prefix. This function preprends the bin/ path and add the binary
        extension to the given list of files
        """
        binaries = {}
        for f in files:
            b = 'bin/%(file)s%(bext)s' % {'file': f, **self.extensions}
            binaries[b] = None
        return binaries

    def _list_libraries(self, files):
        if self.library_type == LibraryType.STATIC:
            return {}
        libs = {}
        for f in files:
            if self.extensions['sregex']:
                pattern = '%(sdir)s/*%(file)s*%(srext)s*'
            else:
                pattern = '%(sdir)s/%(file)s%(srext)s'
            pattern = pattern % {'file': f, **self.extensions}
            libs[pattern] = self._search_library
        return libs

    def _pyfile_get_name(self, f) -> Optional[List[str]]:
        if os.path.exists(Path(self.config.prefix, f).as_posix()):
            return [f]
        for py_prefix in self.py_prefixes:
            original_path = Path(py_prefix, f).as_posix()
            if os.path.exists(Path(self.config.prefix, original_path).as_posix()):
                return [original_path]
            elif '*' in f:
                fs = glob.glob(Path(self.config.prefix, original_path).as_posix(), recursive=True)
                if fs:
                    return [os.path.relpath(f, start=self.config.prefix) for f in fs]
            elif os.path.isabs(f):
                # A files_* entry is not made relative properly
                raise RuntimeError(f'An absolute path "{f}"was supplied, please set relative paths only')

            pydir = os.path.basename(os.path.normpath(py_prefix))
            pyversioname = re.sub(r'python|\.', '', pydir)
            cpythonname = 'cpython-' + pyversioname

            splitedext = os.path.splitext(f)
            for ex in ['', 'm']:
                f = splitedext[0] + '.' + cpythonname + ex + splitedext[1]
                if os.path.exists(Path(self.config.prefix, f).as_posix()):
                    return [f]
        return None

    def _pyfile_get_cached(self, f):
        pyfiles = []
        pycachedir = os.path.join(os.path.dirname(f), '__pycache__')
        for e in ['o', 'c']:
            fe = self._pyfile_get_name(f + e)
            if fe:
                pyfiles.append(fe)
            else:
                cached = os.path.join(pycachedir, os.path.basename(f))
                fe = self._pyfile_get_name(cached)
                if fe:
                    pyfiles.append(fe)

        return pyfiles

    def _list_pyfiles(self, files):
        """
        List python files in the prefix. This function preprends the
        lib/Python$PYVERSION/site-packages/ path to the given list of files
        """
        pyfiles = {}
        files_exts = [f % self.extensions for f in files]
        files = self._list_files(files_exts)
        for f in files:
            real_names = self._pyfile_get_name(f)
            if real_names:
                pyfiles.update({i: None for i in real_names})
            else:
                # Adding it so we notice there is a problem in the recipe
                pyfiles[f] = None
            if f.endswith('.py'):
                cached_files = self._pyfile_get_cached(f)
                for cached_file in cached_files:
                    pyfiles[cached_file] = None
        return pyfiles

    def _list_langfiles(self, files):
        """
        List translations in share/locale/*/LC_MESSAGES/ '
        """
        pattern = 'share/locale/*/LC_MESSAGES/%s.mo'
        langfiles = {}
        for x in files:
            f = pattern % x
            langfiles[f] = None
        return langfiles

    def _list_typelibfiles(self, files):
        """
        List typelibs in lib/girepository-1.0/
        """
        if not self.config.variants.gi:
            return {}

        pattern = '{}/girepository-1.0/%s.typelib'.format(self.extensions['libdir'])
        typelibs = {}
        for x in files:
            file = pattern % x
            typelibs[file] = None
        return typelibs

    def _list_girfiles(self):
        """
        List gir files in share/gir-1.0/
        """
        if not self.config.variants.gi:
            return {}

        girs = []
        if hasattr(self, 'files_' + self.TYPELIB_CAT):
            girs += getattr(self, 'files_' + self.TYPELIB_CAT)
        if hasattr(self, 'platform_files_' + self.TYPELIB_CAT):
            d = getattr(self, 'platform_files_' + self.TYPELIB_CAT)
            girs += d.get(self.config.target_platform, [])

        files = {}
        # Use a * for the arch in universal builds
        pattern = 'share/gir-1.0/%s.gir'
        for gir in girs:
            file = pattern % gir
            files[file] = None
        return files

    def _list_devel_libraries(self):
        return self._list_devel_libraries_by_categories(self.categories)

    def _list_devel_libraries_by_categories(self, categories):
        if self.runtime_dep:
            return ({}, {})

        devel_libs = {}
        pdbs = {}
        skip_pdb_files = set(f % self.extensions for f in getattr(self, 'skip_pdb_files', []))
        for category in categories:
            if category != self.LIBS_CAT and not category.startswith(self.LIBS_CAT + '_'):
                continue

            patterns = []
            if self.library_type != LibraryType.NONE and self.platform == Platform.ANDROID:
                patterns.append('%(libdir)s/%(f)s.la')

            if self.library_type in (LibraryType.BOTH, LibraryType.STATIC):
                patterns.append('%(libdir)s/%(f)s.a')

            if self.library_type in (LibraryType.BOTH, LibraryType.SHARED):
                if self.platform == Platform.LINUX:
                    patterns.append('%(libdir)s/%(f)s.so')
                elif self.platform == Platform.WINDOWS:
                    patterns.append('%(libdir)s/%(f)s.dll.a')
                    patterns.append('%(libdir)s/%(fnolib)s.def')
                    patterns.append('%(libdir)s/%(fnolib)s.lib')
                elif Platform.is_apple(self.platform):
                    patterns.append('%(libdir)s/%(f)s.dylib')

            for x in self._get_category_files_list(category):
                for pattern in patterns:
                    file = pattern % {'f': x, 'fnolib': x[3:], 'libdir': self.extensions['libdir']}
                    devel_libs[file] = None
                if self.have_symbol_files() and self.library_type != LibraryType.STATIC:
                    if x in skip_pdb_files:
                        continue
                    # PDB names are derived from DLL library names (which are
                    # arbitrary), so we must use the same search function for them.
                    if self.using_msvc():
                        pdb = '%(sdir)s/%(f)s%(debugext)s' % {'f': x[3:], **self.extensions}
                    else:
                        pdb = '%(sdir)s/%(f)s%(srext)s%(debugext)s' % {'f': x, **self.extensions}
                    pdbs[pdb] = self._search_library_pdb

        return (devel_libs, pdbs)

    def _ls_dir(self, dirpath):
        files = []
        for root, dirnames, filenames in os.walk(dirpath):
            _root = root.split(self.config.prefix)[1]
            if _root[0] == '/':
                _root = _root[1:]
            files.extend([Path(_root, x).as_posix() for x in filenames])
        return files


class UniversalFilesProvider(FilesProvider):
    wrapped_list_funcs = ['debug_files_list', 'devel_files_list', 'dist_files_list', 'files_list_by_categories']

    def __init__(self, config):
        # Override all public functions that return a list of files.
        for name in dir(FilesProvider):
            if name not in self.wrapped_list_funcs:
                continue
            setattr(self, name, partial(self._aggregate_files_list_func, name))
        self.config = config

    def _aggregate_files_list_func(self, funcname, *args, **kwargs):
        files = []
        for r in self._recipes.values():
            func = getattr(r, funcname)
            rfiles = func(*args, **kwargs)
            for rf in rfiles:
                f = self.get_arch_file(r.config.target_arch, rf)
                files.append(f)
        return files

    def get_arch_file(self, arch, f):
        """
        Layout is split into separate arch-specific prefixes (android-universal)
        """
        return '{}/{}'.format(arch, f)


class UniversalMergedFilesProvider(UniversalFilesProvider):
    def get_arch_file(self, arch, f):
        """
        Layout is one common prefix will all arch-specific files merged into it
        with `lipo` (ios-universal)
        """
        return f
