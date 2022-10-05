# -*- Mode: Python -*- vi:si:et:sw=4:sts=4:ts=4:syntax=python
import os
from collections import defaultdict

from cerbero.build import recipe
from cerbero.build.source import SourceType
from cerbero.build.cookbook import CookBook
from cerbero.enums import License, FatalError

def running_on_cerbero_ci():
    if os.environ.get('CI_PROJECT_NAME', '') != 'cerbero':
        return False
    # If the cerbero CI was triggered from a merge request on the gstreamer
    # monorepo, we want to use git because we want to test the changes that the
    # merge request contains.
    if os.environ.get('CI_GSTREAMER_TRIGGERED', '') == 'true':
        return False
    return True

class GStreamer(recipe.Recipe):
    licenses = [License.LGPLv2Plus]
    version = '1.21.1.1'
    tagged_for_release = False

    # Decide what stype to use
    use_git = True
    if tagged_for_release:
        # If we're using a manifest, that means we want to use the specified
        # commits and remotes.
        use_git = recipe.Recipe._using_manifest_force_git
        # If we're tagged for release and we're running on Cerbero CI, we want
        # to use the release tarballs even if a manifest is specified, because
        # we want to test that the tarballs work.
        if running_on_cerbero_ci():
            use_git = False

    if use_git:
        stype = SourceType.GIT
        remotes = {'origin': 'https://gitlab.freedesktop.org/gstreamer/gstreamer.git'}
        if int(version.split('.')[1]) % 2 == 0:
            # Even version, use the specific branch
            commit = 'origin/' + '.'.join(version.split('.')[0:2])
        else:
            # Odd version, use git main
            commit = 'origin/main'
    else:
        stype = SourceType.TARBALL
        url = 'https://gstreamer.freedesktop.org/src/%(name)s/%(name)s-%(version)s.tar.xz'
        tarball_dirname = '%(name)s-%(version)s'

    def __init__(self, config, env):
        super().__init__(config, env)
        if self.use_git:
            # All GStreamer recipes share the same git repo, but they build a
            # different subproject from it.
            subproject = self.name.replace('-1.0', '')
            self.repo_dir = os.path.abspath(os.path.join(self.config.local_sources, 'gstreamer-1.0'))
            self.config_src_dir = os.path.abspath(os.path.join(self.config.sources, 'gstreamer-1.0'))
            self.build_dir = os.path.join(self.config_src_dir, 'subprojects', subproject)
            # Force using the commit/remotes from 'gstreamer-1.0' recipe, if set
            # in the config, on all gstreamer recipes because they share the same
            # git repository.
            self.commit = self.config.recipe_commit('gstreamer-1.0') or self.commit
            self.remotes.update(self.config.recipes_remotes.get('gstreamer-1.0', {}))
            # gst-integrations-testsuite medias folder is the only submodule in GStreamer repository,
            # disable the submodule to avoid to download more than 500MB of test medias.
            self.use_submodules = False

    def enable_plugin(self, plugin, category, variant=None, option=None, dep=None):
        if option is None:
            option = plugin
        if variant is None or getattr(self.config.variants, variant):
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

    def _remove_files_category_entry(self, files_category, entry):
        if hasattr(self, files_category):
            fc = getattr(self, files_category)
            if entry in fc:
                fc.remove(entry)
                return
        platform_files_category = 'platform_' + files_category
        if hasattr(self, platform_files_category):
            pf = getattr(self, platform_files_category)
            if self.config.target_platform not in pf:
                raise FatalError('plugin {!r} not found in category {!r}'.format(entry, files_category))
            pfc = getattr(self, platform_files_category)[self.config.target_platform]
            if entry in pfc:
                pfc.remove(entry)
                return
        raise FatalError('{} not found in category {}'.format(entry, files_category))

    def _remove_plugin_file(self, plugin, category):
        plugin = 'lib/gstreamer-1.0/libgst' + plugin
        plugin_shared_lib = plugin + '%(mext)s'
        plugin_static_lib = plugin + '.a'
        plugin_libtool_lib = plugin + '.la'
        self._remove_files_category_entry('files_plugins_' + category, plugin_shared_lib)
        self._remove_files_category_entry('files_plugins_{}_devel'.format(category), plugin_static_lib)
        self._remove_files_category_entry('files_plugins_{}_devel'.format(category), plugin_libtool_lib)

    def disable_plugin(self, plugin, category, option=None, dep=None, library_name=None):
        if option is None:
            option = plugin
        if dep is not None and dep in self.deps:
            self.deps.remove(dep)
        self._remove_plugin_file(plugin, category)
        if library_name is not None:
            library = 'libgst' + library_name + '-1.0'
            self.files_libs.remove(library)
            pcname = 'lib/pkgconfig/gstreamer-' + library_name + '-1.0.pc'
            self.files_plugins_devel.remove(pcname)
            includedir = 'include/gstreamer-1.0/gst/' + library_name
            self.files_plugins_devel.remove(includedir)
            libincdir = 'lib/gstreamer-1.0/include/gst/' + library_name
            if libincdir in self.files_plugins_devel:
                self.files_plugins_devel.remove(libincdir)
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
