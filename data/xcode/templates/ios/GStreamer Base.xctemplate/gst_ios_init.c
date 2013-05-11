#include "gst_ios_init.h"

@GST_IOS_PLUGINS_DECLARE@

void
gst_ios_init (void)
{
  GstPluginFeature *plugin;
  GstRegistry *reg;

  gst_init (NULL, NULL);

  @GST_IOS_PLUGINS_REGISTER@


  /* Lower the ranks of filesrc and giosrc so iosavassetsrc is
   * tried first in gst_element_make_from_uri() for file:// */
  reg = gst_registry_get_default();
  plugin = gst_registry_lookup_feature(reg, "filesrc");
  if (plugin)
    gst_plugin_feature_set_rank(plugin, GST_RANK_SECONDARY);
  plugin = gst_registry_lookup_feature(reg, "giosrc");
  if (plugin)
    gst_plugin_feature_set_rank(plugin, GST_RANK_SECONDARY);
}
