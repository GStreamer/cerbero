# -*- Mode: Python -*- vi:si:et:sw=4:sts=4:ts=4:syntax=python
import os
import shutil
from collections import defaultdict

from cerbero.build import recipe
from cerbero.build.source import SourceType
from cerbero.build.cookbook import CookBook
from cerbero.config import Platform
from cerbero.enums import License
from cerbero.utils import shell, to_unixpath

class GStreamer(recipe.Recipe):
    licenses = [License.LGPLv2Plus]
    version = '1.15.0.1'
    commit = 'origin/master'

def list_gstreamer_1_0_plugins_by_category(config):
        cookbook = CookBook(config)
        plugins = defaultdict(list)
        for r in ['gstreamer-1.0', 'gst-plugins-base-1.0', 'gst-plugins-good-1.0',
                  'gst-plugins-bad-1.0', 'gst-plugins-ugly-1.0',
                  'gst-libav-1.0', 'gst-editing-services-1.0', 'gst-rtsp-server-1.0']:
            r = cookbook.get_recipe(r)
            for attr_name in dir(r):
                if attr_name.startswith('files_plugins_'):
                    cat_name = attr_name[len('files_plugins_'):]
                    plugins_list = getattr(r, attr_name)
                elif attr_name.startswith('platform_files_plugins_'):
                    cat_name = attr_name[len('platform_files_plugins_'):]
                    plugins_dict = getattr(r, attr_name)
                    plugins_list = plugins_dict.get(config.target_platform, [])
                else:
                    continue
                for e in plugins_list:
                    if not e.startswith('lib/gstreamer-'):
                        continue
                    c = e.split('/')
                    if len(c) != 3:
                        continue
                    e = c[2]
                    # we only care about files with the replaceable %(mext)s extension
                    if not e.endswith ('%(mext)s'):
                        continue
                    if e.startswith('libgst'):
                        e = e[6:-8]
                    else:
                        e = e[3:-8]
                    plugins[cat_name].append(e)
        return plugins
