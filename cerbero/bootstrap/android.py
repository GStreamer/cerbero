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
import shutil

from cerbero.bootstrap import BootstrapperBase
from cerbero.bootstrap.bootstrapper import register_bootstrapper
from cerbero.config import Distro, FatalError
from cerbero.utils import _, shell

NDK_VERSION = 'r16'
NDK_BASE_URL = 'https://dl.google.com/android/repository/android-ndk-%s-%s-%s.zip'
NDK_CHECKSUMS = {
    'android-ndk-r16-linux-x86_64.zip': 'a8550b81771c67cc6ab7b479a6918d29aa78de3482901762b4f9e0132cd9672e',
    'android-ndk-r16-darwin-x86_64.zip': '589a567c4fc84f5f7219cae56d199b63059033e08512b6d8132739c90ef9483d',
    'android-ndk-r16-windows-x86_64.zip': 'fb4ce0bbcb927dc1bb507d3dbb1aef0f243e5184b3dd5d956a450bcf4b0808df',
    'android-ndk-r16-windows-x86.zip': 'aaa52b9e8b283be1249376f7373704687a5b13106575f613378e6d44c663f782',
}

class AndroidBootstrapper (BootstrapperBase):


    def __init__(self, config, offline):
        super().__init__(config, offline)
        self.prefix = self.config.toolchain_prefix
        url = NDK_BASE_URL % (NDK_VERSION, self.config.platform, self.config.arch)
        self.fetch_urls.append((url, NDK_CHECKSUMS[os.path.basename(url)]))
        self.extract_steps.append((url, True, self.prefix))

    def start(self):
        if not os.path.exists(self.prefix):
            os.makedirs(self.prefix)
        ndkdir = os.path.join(self.prefix, 'android-ndk-' + NDK_VERSION)
        if not os.path.isdir(ndkdir):
            return
        # Android NDK extracts to android-ndk-$NDK_VERSION, so move its
        # contents to self.prefix
        for d in os.listdir(ndkdir):
            dest = os.path.join(self.prefix, d)
            if os.path.exists(dest):
                shutil.rmtree(dest)
            shutil.move(os.path.join(ndkdir, d), self.prefix)
        os.rmdir(ndkdir)


def register_all():
    register_bootstrapper(Distro.ANDROID, AndroidBootstrapper)
