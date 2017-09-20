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

class GStreamerBase:

    licenses = [License.LGPLv2Plus]
    version = '1.12.4'
    commit = '1.12.4'

class GStreamer(GStreamerBase, recipe.Recipe):

    pass

class GStreamerStatic(GStreamerBase, recipe.Recipe):

    gstreamer_version = '1.0'
    configure_options = "--enable-introspection=no --disable-examples --enable-static-plugins --disable-shared --enable-static "
    extra_configure_options = ''
    # Static build will always fail on make check
    make_check = None

    def prepare(self):
        self.project_name = self.name.replace('-static', '')
        if self.stype in (SourceType.GIT, SourceType.GIT_TARBALL):
            self.config_sh = 'sh ./autogen.sh --noconfigure && ./configure'
            self.repo_dir = os.path.join(self.config.local_sources,
                                         self.project_name)
        elif self.stype == SourceType.TARBALL:
            # Ensure that the correct unpacked directory is used 
            # as the build directory
            self.build_dir = os.path.join(os.path.dirname(self.build_dir),
                                          '{0}-{1}'.format(self.project_name,
                                                           self.version))
        else:
            raise Exception("Static recipes only work with GIT, GIT_TARBALL, and TARBALL SourceTypes")

        if self.config.target_platform != Platform.LINUX:
            self.configure_options += ' --disable-gtk-doc'
        self.configure_options += ' ' + self.extra_configure_options

        self.tmp_destdir = os.path.join(self.build_dir, 'static-build')
        self.make_install = 'make install DESTDIR=%s' % self.tmp_destdir

        # Fill the list of files with the static library and the libtool link
        # library, libgstplugin.a and libgstplugin.la
        self.plugins_categories = [x for x in dir(self) if
                x.startswith('files_plugins')]
        self.platform_plugins_categories = [x for x in dir(self) if
                x.startswith('platform_files_plugins')]
        self._files_list = []
        plugin_path = 'lib/gstreamer-%s/static' % self.gstreamer_version
        for name in self.plugins_categories:
            files = getattr(self, name)
            f = ['%s/%s.a' % (plugin_path, x) for x in files]
            f.extend(['%s/%s.la' % (plugin_path, x) for x in files])
            setattr(self, name, f)
            self._files_list.extend(f)
        for name in self.platform_plugins_categories:
            platform_files = getattr(self, name)
            files = platform_files.get(self.config.target_platform, [])
            f = ['%s/%s.a' % (plugin_path, x) for x in files]
            f.extend(['%s/%s.la' % (plugin_path, x) for x in files])
            platform_files[self.config.target_platform] = f
            self._files_list.extend(f)
        self.append_env ['CFLAGS'] = "%s %s" % (self.append_env.get('CFLAGS',
            ''), '-fPIC -DPIC')
        self.append_env ['CXXFLAGS'] = "%s %s" % (self.append_env.get('CXXFLAGS',
            ''), '-fPIC -DPIC')

    def configure(self):
        if not os.path.exists(self.tmp_destdir):
            os.makedirs(self.tmp_destdir)
        self.btype.configure(self)

    def post_install(self):
        if not self._files_list:
            return
        plugins_dir = os.path.dirname(os.path.join(self.config.prefix,
                                                   self._files_list[0]))
        if not os.path.exists(plugins_dir):
            os.makedirs(plugins_dir)
        # Copy all files installed in the temporary build-static directory
        # to the prefix. Static plugins will be installed in
        # lib/gstreamer-1.0/static to avoid conflicts with the libgstplugin.la
        # generated with the shared build
        for f in self._files_list:
            src = os.path.join(self.tmp_destdir,
                    to_unixpath(self.config.prefix)[1:],
                    f.replace('/static/', '/'))
            dest = os.path.join(self.config.prefix, f)
            if f.endswith('.la'):
                shell.call('sed -i "s#^libdir=\'\(.*\)\'#libdir=\'\\1/static\'#" %s' % src)
            shutil.copyfile(src, dest)


def list_gstreamer_plugins_by_category(config):
        cookbook = CookBook(config)
        # For plugins named differently
        replacements = {'decodebin2': 'uridecodebin', 'playbin': 'playback',
                        'encodebin': 'encoding', 'souphttpsrc': 'soup',
                        'siren': 'gstsiren', 'sdpelem': 'sdp',
                        'rtpmanager': 'gstrtpmanager', 'scaletempoplugin' : 'scaletempo',
                        'mpegdemux': 'mpegdemux2', 'rmdemux': 'realmedia'}
        plugins = defaultdict(list)
        for r in ['gstreamer', 'gst-plugins-base', 'gst-plugins-good',
                  'gst-plugins-bad', 'gst-plugins-ugly', 'gst-ffmpeg', 'gst-rtsp-server']:
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
                    plugins[cat_name].append(e[25:-8])
        return plugins, replacements

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
                    if e.startswith('libgst'):
                        e = e[6:-8]
                    else:
                        e = e[3:-8]
                    plugins[cat_name].append(e)
        return plugins
