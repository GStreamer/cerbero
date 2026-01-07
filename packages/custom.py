# -*- Mode: Python -*- vi:si:et:sw=4:sts=4:ts=4:syntax=python

from cerbero.enums import CERBERO_VERSION, License


class GStreamer:
    url = 'http://gstreamer.freedesktop.org'
    version = CERBERO_VERSION
    vendor = 'GStreamer Project'
    licenses = [License.LGPLv2Plus]
    org = 'org.freedesktop.gstreamer'
