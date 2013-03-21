
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
%s
%s
%s
</plist>
'''


class Plist(object):
    ''' Base class for creating .plist files '''

    BEGIN = '<array>\n<dict>\n'
    END = '</dict>\n</array>\n'

    def save(self, filename):
        props_str = self._get_properties_string()
        with open(filename, 'w+') as f:
            f.write(INFO_PLIST_TPL  % (self.BEGIN, props_str, self.END))

    def _format_property(self, key, value):
        if isinstance(value, str):
            return '<key>%s</key>\n<string>%s</string>' % (key, value)
        elif isinstance(value, bool):
            return '<key>%s</key>\n<%s/>' % (key, str(value).lower())
        else:
            raise Exception ("Invalid type for value %r", value)

    def _get_properties(self):
        raise NotImplementedError("get_properties not implemented")

    def _get_properties_string(self):
        props = self._get_properties()
        return '\n'.join([self._format_property(k, props[k]) for k in
                          sorted(props.keys())])


class InfoPlist(Plist):
    ''' Create a Info.plist file '''

    BEGIN = '<dict>\n'
    END = '</dict>\n'
    package_type = ''

    def __init__(self, name, identifier, version, info, icon=None):
        self.name = name
        self.identifier = identifier
        self.version = version
        self.info = info
        self.icon = icon

    def _get_properties(self):
        properties = {'CFBundleName': self.name,
                'CFBundleIdentifier': self.identifier,
                'CFBundleVersion': self.version,
                'CFBundlePackageGetInfoString': self.info,
                'CFBundlePackageType': self.package_type}
        if self.icon:
            properties['CFBundleIconFile'] = self.icon
        return properties


class FrameworkPlist(InfoPlist):
    ''' Create a Info.plist file for frameworks '''

    package_type = 'FMWK'



class ApplicationPlist(InfoPlist):
    ''' Create a Info.plist file for applications '''

    package_type = 'APPL'


class ComponentPropertyPlist(Plist):
    ''' Create a component property list to be used with pkgbuild '''

    def __init__(self, description, rel_path):
        self.desc = description
        self.rel_path = rel_path

    def _get_properties(self):
        return {'BundlerIsVersionChecked': True,
                'BundleOverwriteAction': 'upgrade',
                'RootRelativeBundlePath': self.rel_path,
                'Key': self.desc}
