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


class PropsBase(object):

    def __init__(self, name):
        self.name = name
        self._add_root()
        self._add_skeleton()

    def _add_root(self):
        self.root = etree.Element('Project', ToolsVersion='4.0',
                xmlns='http://schemas.microsoft.com/developer/msbuild/2003')

    def _add_skeleton(self):
        self.import_group = etree.SubElement(self.root, 'ImportGroup',
                Label='PropertySheets')
        self.user_macros_group = etree.SubElement(self.root, 'PropertyGroup',
                Label='UserMacros')
        self.property_group = etree.SubElement(self.root, 'PropertyGroup')
        self.item_definition_group = etree.SubElement(self.root,
                'ItemDefinitionGroup')
        self.item_group = etree.SubElement(self.root, 'ItemGroup')

    def _add_macro(self, name, value):
        m = etree.SubElement(self.user_macros_group, name)
        m.text = value
        bm = etree.SubElement(self.item_group, 'BuildMacro', Include=name)
        val = etree.SubElement(bm, 'Value')
        val.text = '$(%s)' % name
        ev = etree.SubElement(bm, 'EnvironmentVariable')
        ev.text = 'true'

    def _import_property(self, name):
        cond = '$(%sImported)!=true' % self._format_name(name)
        etree.SubElement(self.import_group, 'Import', Condition=cond,
                         Project='%s.props' % name)

    def create(self, outdir):
        el = etree.ElementTree(self.root)
        el.write(os.path.join(outdir, '%s.props' % self.name),
                 encoding='utf-8', pretty_print=True)

    def _add_compiler_props(self):
        self.compiler = etree.SubElement(self.item_definition_group,
                'ClCompile')

    def _add_linker_props(self):
        self.linker = etree.SubElement(self.item_definition_group, 'Link')

    def _add_include_dirs(self, dirs):
        self._add_var(self.compiler, 'AdditionalIncludeDirectories',
            self._format_paths(dirs))

    def _add_libs_dirs(self, dirs):
        self._add_var(self.linker, 'AdditionalLibraryDirectories',
            self._format_paths(dirs))

    def _add_libs(self, libs):
        self._add_var(self.linker, 'AdditionalDependencies',
            self._format_libs(libs))

    def _add_imported_variable(self):
        el = etree.SubElement(self.property_group, '%sImported' %
                              self._format_name(self.name))
        el.text = 'true'

    def _add_var(self, parent, name, content):
        el = etree.SubElement(parent, name)
        el.text = content + ';%%(%s)' % name

    def _format_libs(self, libs):
        return ';'.join(['%s.lib' % x for x in libs])

    def _format_paths(self, paths):
        return ';'.join([self._fix_path_and_quote(x) for x in paths])

    def _fix_path_and_quote(self, path):
        return to_winpath(path)

    def _format_name(self, name):
        name = name.replace('+', '_').replace('-', '_').replace('.', '_')
        return name


class CommonProps(PropsBase):

    def __init__(self, prefix_macro):
        PropsBase.__init__(self, 'Common')
        self._add_root()
        self._add_skeleton()
        self._add_compiler_props()
        self._add_include_dirs(['$(%s)\include' % prefix_macro])
        self._add_imported_variable()


class Props(PropsBase):
    '''
    Creates a MSBUILD properties sheet that imitaties a pkgconfig files to link
    against a library from VS:
      * inherits from others properties sheets
      * add additional includes directories
      * add additional libraries directories
      * add link libraries
    '''

    def __init__(self, name, requires, include_dirs, libs_dirs, libs,
                 inherit_common=False):
        PropsBase.__init__(self, name)
        if inherit_common:
            requires.append('Common')
        for require in requires:
            self._import_property(require)
        self._add_compiler_props()
        self._add_linker_props()
        self._add_include_dirs(include_dirs)
        self._add_libs_dirs(libs_dirs)
        self._add_libs(libs)
        self._add_imported_variable()
