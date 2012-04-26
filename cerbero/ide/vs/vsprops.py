#!/usr/bin/env python
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
from cerbero.utils import etree, to_winpath


class VSPropsBase(object):

    def __init__(self, name):
        self.name = name

    def _add_root(self, name):
        self.root = etree.Element("VisualStudioPropertySheet",
                ProjectType="Visual C++", Version="8.00", Name=name)

    def create(self, outdir):
        el = etree.ElementTree(self.root)
        el.write(os.path.join(outdir, '%s.vsprops' % self.name),
                 encoding='utf-8')


class CommonVSProps(VSPropsBase):

    def __init__(self, prefix, prefix_macro):
        VSPropsBase.__init__(self, 'Common')
        self._add_root('Common')
        self._add_sdk_root_macro(prefix, prefix_macro)

    def _add_sdk_root_macro(self, prefix, prefix_macro):
        etree.SubElement(self.root, 'Macro', Name=prefix_macro,
                         Value=to_winpath(prefix))


class VSProps(VSPropsBase):
    '''
    Creates an VS properties sheet that imitaties a pkgconfig files to link
    against a library from VS:
      * inherits from others properties sheets
      * add additional includes directories
      * add additional libraries directories
      * add link libraries
    '''

    def __init__(self, name, requires, include_dirs, libs_dirs, libs,
                 inherit_common=False):
        VSPropsBase.__init__(self, name)
        if inherit_common:
            requires.append('Common')
        self._add_root(name, requires)
        self.root.set('InheritedPropertySheets',
                      self._format_requires(requires))
        self._add_include_dirs(include_dirs)
        self._add_libs(libs, libs_dirs)

    def _add_root(self, name, requires):
        VSPropsBase._add_root(self, name)
        self.root.set('InheritedPropertySheets',
                      self._format_requires(requires))

    def _add_include_dirs(self, dirs):
        self._add_tool("VCCLCompilerTool",
                       AdditionalIncludeDirectories=self._format_paths(dirs))

    def _add_libs(self, libs, dirs):
        self._add_tool("VCLinkerTool",
                       AdditionalDependencies=self._format_libs(libs),
                       AdditionalLibraryDirectories=self._format_paths(dirs))

    def _format_requires(self, requires):
        return ';'.join([".\\%s.vsprops" % x for x in requires])

    def _format_libs(self, libs):
        return ' '.join(['%s.lib' % x for x in libs])

    def _format_paths(self, paths):
        return ';'.join([self._fix_path_and_quote(x) for x in paths])

    def _fix_path_and_quote(self, path):
        path = to_winpath(path)
        return "&quot;%s&quot;" % path

    def _add_tool(self, name, **kwargs):
        etree.SubElement(self.root, 'Tool', Name=name, **kwargs)
