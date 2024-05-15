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

from cerbero.config import Config


class DummyConfig(Config):
    def __init__(self, is_build_tools_config=False):
        super().__init__(is_build_tools_config=is_build_tools_config)
        self.load()


class XMLMixin:
    def find_one(self, el, tag):
        children = list(el.iterfind(tag))
        if len(children) == 0:
            self.fail('Element with tag %s not found in parent %s' % (tag, el))
        return children[0]

    def check_attrib(self, parent, tag, attrib, value):
        n = self.find_one(parent, tag)
        if attrib not in n.attrib:
            self.fail('Attribute %s not found in %s' % (attrib, n))
        self.assertEqual(n.attrib[attrib], value)

    def check_text(self, parent, tag, value):
        n = self.find_one(parent, tag)
        self.assertEqual(n.text, value)
