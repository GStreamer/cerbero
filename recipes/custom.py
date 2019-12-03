# -*- Mode: Python -*- vi:si:et:sw=4:sts=4:ts=4:syntax=python
import os
import shutil
from collections import defaultdict

from cerbero.build import recipe
from cerbero.build.source import SourceType
from cerbero.build.cookbook import CookBook
from cerbero.enums import Platform, License
from cerbero.utils import shell, to_unixpath

class GStreamer(recipe.Recipe):
    licenses = [License.LGPLv2Plus]
    version = '1.16.2'
    tagged_for_release = True

    if not tagged_for_release or recipe.Recipe._using_manifest_force_git:
        # Pre-release version, use git master
        stype = SourceType.GIT
        remotes = {'origin': 'https://gitlab.freedesktop.org/gstreamer/%(name)s.git'}
        if int(version.split('.')[1]) % 2 == 0:
            # Even version, use the specific branch
            commit = 'origin/' + '.'.join(version.split('.')[0:2])
        else:
            # Odd version, use git master
            commit = 'origin/master'
    else:
        # Release version, use tarballs
        stype = SourceType.TARBALL
        url = 'https://gstreamer.freedesktop.org/src/%(name)s/%(name)s-%(version)s.tar.xz'
        tarball_dirname = '%(name)s-%(version)s'
        # Always define `commit`, used by gst-validate
        commit = version

    def enable_plugin(self, plugin, category, variant, option=None, dep=None):
        if option is None:
            option = variant
        if getattr(self.config.variants, variant):
            if dep is not None:
                self.deps.append(dep)
            plugin = 'lib/gstreamer-1.0/libgst' + plugin
            if not hasattr(self, 'files_plugins_' + category):
                setattr(self, 'files_plugins_' + category, [])
            f = getattr(self, 'files_plugins_' + category)
            f += [plugin + '%(mext)s']
            if not hasattr(self, 'files_plugins_{}_devel'.format(category)):
                setattr(self, 'files_plugins_{}_devel'.format(category), [])
            d = getattr(self, 'files_plugins_{}_devel'.format(category))
            d += [plugin + '.a', plugin + '.la']
            self.meson_options[option] = 'enabled'
        else:
            self.meson_options[option] = 'disabled'

    def disable_plugin(self, plugin, category, option=None, dep=None):
        if option is None:
            option = plugin
        if dep is not None and dep in self.deps:
            self.deps.remove(dep)
        plugin = 'lib/gstreamer-1.0/libgst' + plugin
        if hasattr(self, 'files_plugins_' + category):
            f = getattr(self, 'files_plugins_' + category)
            f.remove(plugin + '%(mext)s')
        if hasattr(self, 'files_plugins_{}_devel'.format(category)):
            d = getattr(self, 'files_plugins_{}_devel'.format(category))
            d.remove(plugin + '.a')
            d.remove(plugin + '.la')
        self.meson_options[option] = 'disabled'


def list_gstreamer_1_0_plugins_by_category(config):
        cookbook = CookBook(config)
        plugins = defaultdict(list)
        for r in ['gstreamer-1.0', 'gst-plugins-base-1.0', 'gst-plugins-good-1.0',
                  'gst-plugins-bad-1.0', 'gst-plugins-ugly-1.0', 'libnice',
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
