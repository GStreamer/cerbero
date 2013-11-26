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

import _winreg as winreg
import os

from cerbero.config import Architecture
from cerbero.utils import fix_winpath, shell


class MSBuild(object):

    def __init__(self, solution, arch=Architecture.X86, config='Release',
                 sdk='Windows7.1SDK', **properties):
        self.properties = {}
        if arch == Architecture.X86:
            self.properties['Platform'] = 'Win32'
        elif arch == Architecture.X86_64:
            self.properties['Platform'] = 'x64'
        self.properties['Configuration'] = config
        self.properties['PlatformToolset'] = sdk
        self.properties.update(properties)
        self.solution = solution

    def build(self):
        self._call('build')

    @staticmethod
    def get_msbuild_tools_path():
        reg = winreg.ConnectRegistry(None, winreg.HKEY_LOCAL_MACHINE)
        key = winreg.OpenKey(reg,
                r"SOFTWARE\Microsoft\MSBuild\ToolsVersions\4.0")
        path = winreg.QueryValueEx(key, 'MSBuildToolsPath')[0]
        return fix_winpath(path)

    @staticmethod
    def get_vs_path():
        reg = winreg.ConnectRegistry(None, winreg.HKEY_LOCAL_MACHINE)
        key = winreg.OpenKey(reg,
                r"SOFTWARE\Microsoft\VisualStudio\SxS\VC7")
        path = winreg.QueryValueEx(key, '10.0')[0]
        path = str(path)
        path = path.replace('\\VC', '\\Common7\\IDE')
        return path

    def _call(self, command):
        properties = self._format_properties()
        msbuildpath = self.get_msbuild_tools_path()
        vs_path = self.get_vs_path()
        old_path = os.environ['PATH']
        if self.properties['Platform'] == 'Win32':
            os.environ['PATH'] = '%s;%s' % (os.environ['PATH'], vs_path)
        try:
            shell.call('msbuild.exe %s %s /target:%s' %
                       (self.solution, properties, command), msbuildpath)
        finally:
            os.environ['PATH'] = old_path

    def _format_properties(self):
        props = ['/property:%s=%s' % (k, v) for k, v in
                 self.properties.iteritems()]
        return ' '.join(props)
