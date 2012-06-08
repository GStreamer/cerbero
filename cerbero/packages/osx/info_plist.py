
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
       <key>CFBundleName</key>
       <string>%(name)s</string>
       <key>CFBundleIdentifier</key>
       <string>%(identifier)s</string>
       <key>CFBundleVersion</key>
       <string>%(version)s</string>
       <key>CFBundleSignature</key>
       <string>????</string>
       <key>CFBundlePackageType</key>
       <string>FMWK</string>
       <key>CFBundleGetInfoString</key>
       <string>%(info)s</string>
</dict>
</plist>
'''


class FrameworkPlist(object):
    ''' Create a Info.plist file with the framework info '''

    def __init__(self, name, identifier, version, info):
        self.name = name
        self.identifier = identifier
        self.version = version
        self.info = info

    def save(self, filename):
        props = {'name': self.name, 'identifier': self.identifier,
                'version': self.version, 'info': self.info}
        with open(filename, 'w+') as f:
            f.write(INFO_PLIST_TPL  % props)

