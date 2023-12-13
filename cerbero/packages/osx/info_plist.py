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

INFO_PLIST_TPL = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
<key>CFBundleIdentifier</key>
<string>%(id)s</string>
<key>CFBundleName</key>
<string>%(name)s</string>
<key>CFBundleExecutable</key>
<string>%(name)s</string>
<key>CFBundlePackageGetInfoString</key>
<string>%(desc)s</string>
<key>CFBundlePackageType</key>
<string>%(ptype)s</string>
<key>CFBundleVersion</key>
<string>%(version)s</string>
<key>CFBundleShortVersionString</key>
<string>%(version_str)s</string>
<key>LSMinimumSystemVersion</key>
<string>%(minosxversion)s</string>
<key>CFBundleInfoDictionaryVersion</key>
<string>6.0</string>
%(extra)s
</dict>
</plist>
"""


class InfoPlist(object):
    """Create a Info.plist file"""

    package_type = ''

    def __init__(self, name, identifier, version, info, minosxversion, icon=None, plist_tpl=None):
        self.name = name
        self.identifier = identifier
        self.version = version
        self.minosxversion = minosxversion
        self.info = info
        self.icon = icon
        self.plist_tpl = plist_tpl or INFO_PLIST_TPL

    def save(self, filename):
        with open(filename, 'w+') as f:
            f.write(self.plist_tpl % self._get_properties())

    def _get_properties(self):
        properties = {
            'id': self.identifier,
            'name': self.name,
            'desc': self.info,
            'ptype': self.package_type,
            'icon': self.icon,
            'version_str': self.version,
            'version': self.version.replace('.', ''),
            'minosxversion': self.minosxversion,
            'extra': '',
        }
        if self.icon:
            properties['extra'] = '<key>CFBundleIconFile</key>\n' '<string>%s</string>' % self.icon
        return properties


class FrameworkPlist(InfoPlist):
    """Create a Info.plist file for frameworks"""

    package_type = 'FMWK'


class ApplicationPlist(InfoPlist):
    """Create a Info.plist file for applications"""

    package_type = 'APPL'


class ComponentPropertyPlist:
    """Create a component property list to be used with pkgbuild"""

    COMPONENT_TPL = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<array>
<dict>
<key>BundlerIsVersionChecked</key>
<string>True<string>
<key>BundleOverwriteAction</key>
<string>upgrade<string>
<key>RootRelativeBundlePath</key>
<string>%s<string>
<key>Key</key>
<string>%s<string>
</dict>
</array>
</plist>
"""

    def __init__(self, description, rel_path):
        self.desc = description
        self.rel_path = rel_path

    def save(self, filename):
        with open(filename, 'w+') as f:
            f.write(INFO_PLIST_TPL % (self.rel_path, self.key))
