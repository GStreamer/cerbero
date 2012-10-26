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

from cerbero.bootstrap import BootstraperBase
from cerbero.bootstrap.bootstraper import register_bootstraper
from cerbero.config import Distro
from cerbero.utils import shell


class AndroidBootstraper (BootstraperBase):

    NDK_BASE_URL = 'http://dl.google.com/android/ndk/'
    NDK_TAR = 'android-ndk-r8b-linux-x86.tar.bz2'

    def start(self):
        dest = self.config.toolchain_prefix
        tar = os.path.join(dest, self.NDK_TAR)
        if os.path.exists(dest):
            shutil.rmtree(dest)
        os.makedirs(dest)
        shell.download("%s/%s" % (self.NDK_BASE_URL, self.NDK_TAR), tar)
        try:
            shell.unpack(tar, os.path.join(dest))
            shell.call('mv android-ndk-r8b/* .', dest)
        except Exception:
            pass


def register_all():
    register_bootstraper(Distro.ANDROID, AndroidBootstraper)
