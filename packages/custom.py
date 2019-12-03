# -*- Mode: Python -*- vi:si:et:sw=4:sts=4:ts=4:syntax=python

from cerbero.packages import package
from cerbero.enums import License

class GStreamer:

    url = "http://gstreamer.freedesktop.org"
    version = '1.16.2'
    vendor = 'GStreamer Project'
    licenses = [License.LGPLv2Plus]
    org = 'org.freedesktop.gstreamer'
