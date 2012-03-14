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

from cerbero.config import Platform
from cerbero.utils import shell


class Package(object):
    '''
    Describes a set of files to produce disctribution packages for the different
    target platforms

    @cvar name: name of the package
    @type name: str
    @cvar shortdesc: Short description of the package
    @type shortdesc: str
    @cvar longdesc: Long description of the package
    @type longdesc: str
    @cvar version: version of the package
    @type version: str
    @cvar licenses:  list of the package linceses
    @type licenses: list
    @cvar vendor: vendor for this package
    @type vendor: str
    @cvar libraries: list of libraries
    @type libraries: list
    @cvar platform_libs: list of platform dependant libraries
    @type platform_libs: dict
    @cvar binaries: list of binaries
    @type binaries: list
    @cvar platform_bins: list of platform dependant binaries
    @type platform_bins: dict
    @cvar files: list of files included in this package
    @type type: files
    @cvar platform_files: list of files included for a specific platform
    @type type: dict

    @ivar extensions: file extensions for binaries and shared libraries
    @type bext: dict
    '''

    name = ''
    shortdesc = ''
    longdesc = ''
    version = ''
    licenses = list()
    vendor = ''
    libraries = list()
    platform_libs = {}
    binaries = list()
    platform_bins = {}
    files = list()
    platform_files = {}

    EXTENSIONS = {
        Platform.WINDOWS: {'bext': '.exe', 'sext': '.dll', 'sdir': 'bin'},
        Platform.LINUX: {'bext': '', 'sext': '.so', 'sdir': 'lib'},
        Platform.DARWIN: {'bext': '', 'sext': '.dylib', 'sdir': 'lib'}}

    def __init__(self, config):
        self.config = config
        self.extensions = self.EXTENSIONS[self.config.target_platform]

    def get_files_list(self):
        files = []
        files.extend(self._get_files())
        files.extend(self._get_binaries())
        files.extend(self._get_libraries())
        return files

    def _get_files(self):
        # Fille the list of regular files
        files = self.files
        if self.config.target_platform in self.platform_files:
            files.extend(self.platform_files[self.config.target_platform])
        return [f % self.extensions for f in files]

    def _get_binaries(self):
        files = []
        # Fill the list of binaries
        binaries = self.binaries
        if self.config.target_platform in self.platform_bins:
            binaries.extend(self.platform_bins[self.config.target_platform])
        for f in binaries:
            self.extensions['file'] = f
            files.append('bin/%(file)s%(bext)s' % self.extensions)
        return files

    def _get_libraries(self):
        # Fill the list of binaries
        # Unfortunately the filename might vary depending on the platform and we
        # need to match the library name and it's extension with the list of
        # files in the prefix
        libraries = self.libraries
        if self.config.target_platform in self.platform_libs:
            libraries.extend(self.platform_libs[self.config.target_platform])
        libsmatch = []
        for f in libraries:
            self.extensions['file'] = f
            libsmatch.append('%(sdir)s/%(file)s*%(sext)s' % self.extensions)
        # FIXME: I think's that's the fastest way of getting the list of
        # libraries that matches the library name
        sfiles = shell.check_call('ls %s' % ' '.join(libsmatch),
                                 self.config.prefix, True, False, False).split('\n')
        sfiles.remove('')
        return sfiles
