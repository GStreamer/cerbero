
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

INFO_PLIST_TPL='''\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
%s
</dict>
</plist>
'''


class InfoPlist(object):
    ''' Create a Info.plist file '''

    package_type = ''

    def __init__(self, name, identifier, version, info, icon=None):
        self.name = name
        self.identifier = identifier
        self.version = version
        self.info = info
        self.icon = icon

    def format_property(self, key, value):
        return '<key>%s</key>\n<string>%s</string>' % (key, value)

    def get_properties(self):
        properties = {'CFBundleName': self.name,
                'CFBundleIdentifier': self.identifier,
                'CFBundleVersion': self.version,
                'CFBundlePackageGetInfoString': self.info,
                'CFBundlePackageType': self.package_type}
        if self.icon:
            properties['CFBundleIconFile'] = self.icon
        return properties

    def get_properties_string(self):
        props = self.get_properties()
        return '\n'.join([self.format_property(k, props[k]) for k in
                          sorted(props.keys())])

    def save(self, filename):
        props_str = self.get_properties_string()
        with open(filename, 'w+') as f:
            f.write(INFO_PLIST_TPL  % props_str)


class FrameworkPlist(InfoPlist):
    ''' Create a Info.plist file for frameworks '''

    package_type = 'FMWK'



class ApplicationPlist(InfoPlist):
    ''' Create a Info.plist file for applications '''

    package_type = 'APPL'
